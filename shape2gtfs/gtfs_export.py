import csv
import gettext
import os
import re

from collections import namedtuple, Iterable
from datetime import datetime, timedelta
from zipfile import ZipFile

GtfsFeedInfo = namedtuple('GtfsFeedInfo', 'feed_id feed_publisher_name feed_publisher_url feed_lang feed_version')
GtfsAgency = namedtuple('GtfsAgency', 'agency_id agency_name agency_url agency_timezone agency_lang agency_email')
GtfsRoute = namedtuple('GtfsRoute',  'agency_id route_id route_long_name route_type route_url route_short_name')
GtfsStop = namedtuple('GtfsStop', 'stop_id stop_lat stop_lon stop_name')
GtfsStopTime = namedtuple('GtfsStopTime', 'trip_id departure_time arrival_time stop_id stop_sequence pickup_type drop_off_type timepoint')
GtfsTrip = namedtuple('GtfsTrip', 'route_id trip_id service_id shape_id trip_headsign bikes_allowed')
GtfsFrequency = namedtuple('GtfsFrequency', 'trip_id start_time end_time headway_secs exact_times')
GtfsCalendar = namedtuple('GtfsCalendar', 'service_id start_date end_date monday tuesday wednesday thursday friday saturday sunday')
GtfsCalendarDate = namedtuple('GtfsCalendarDate', 'service_id date exception_type')
GtfsShape = namedtuple('GtfsShape','shape_id shape_pt_lat shape_pt_lon shape_pt_sequence')

class GtfsExport:
	NO_BIKES_ALLOWED = 2
	CALENDAR_DATES_EXCEPTION_TYPE_ADDED = 1
	CALENDAR_DATES_EXCEPTION_TYPE_REMOVED = 2
	STOP_TIMES_STOP_TYPE_REGULARLY = 0
	STOP_TIMES_STOP_TYPE_NONE = 1
	STOP_TIMES_STOP_TYPE_PHONE_AGENCY = 2
	STOP_TIMES_STOP_TYPE_COORDINATE_DRIVER = 3
	STOP_TIMES_TIMEPOINT_APPROXIMATE = 0 
	STOP_TIMES_TIMEPOINT_EXACT = 1
	FREQUENCY_EXACT_TIMES_NO = 0
	FREQUENCY_EXACT_TIMES_YES = 1
	
	
	stops_counter = 0
	trips_counter = 0
	routes_counter = 0
	
	def __init__(self, agencies, feed_info, stopstore):
		self.stops = {}
		self.routes = []
		self.calendar_dates = []
		self.calendar = []
		self.trips = []
		self.frequencies = []
		self.stop_times = []
		self.calendar = []
		self.shapes = []
		self.agencies = agencies
		self.feed_info = feed_info
		self.stopstore = stopstore
			
	def export(self, gtfszip_filename, gtfsfolder):
		if not os.path.exists(gtfsfolder):
			os.makedirs(gtfsfolder)
		self.write_csvfile(gtfsfolder, 'agency.txt', self.agencies)
		self.write_csvfile(gtfsfolder, 'feed_info.txt', self.feed_info)
		self.write_csvfile(gtfsfolder, 'routes.txt', self.routes)
		self.write_csvfile(gtfsfolder, 'trips.txt', self.trips)
		self.write_csvfile(gtfsfolder, 'frequencies.txt', self.frequencies)
		self.write_csvfile(gtfsfolder, 'calendar.txt', self.calendar)
		self.write_csvfile(gtfsfolder, 'calendar_dates.txt', self.calendar_dates)
		self.write_csvfile(gtfsfolder, 'stops.txt', self.stops.values())
		self.write_csvfile(gtfsfolder, 'stop_times.txt', self.stop_times)
		self.write_csvfile(gtfsfolder, 'shapes.txt', self.shapes)
		self.zip_files(gtfszip_filename, gtfsfolder)
	
	def zip_files(self, gtfszip_filename, gtfsfolder):
		gtfsfiles = ['agency.txt', 'feed_info.txt', 'routes.txt', 'trips.txt', 'frequencies.txt',
			'calendar.txt', 'stops.txt', 'stop_times.txt', 'shapes.txt']
		if self.calendar_dates:
			gtfsfiles.append('calendar_dates.txt')

		with ZipFile(gtfszip_filename, 'w') as gtfszip:
			for gtfsfile in gtfsfiles:
				gtfszip.write(gtfsfolder+'/'+gtfsfile, gtfsfile)
	
	def convert_route(self, route):
		self.routes_counter += 1
		self.routes.append(self.create_route(self.routes_counter, route))
		self.calendar.append(self.create_calendar(self.routes_counter, route))
		if not route.runs_regularly:
			self.calendar_dates.append(self.create_calendar_date(self.routes_counter, route))
		self.trips.append(self.create_trip(self.routes_counter, self.trip_headsign(route)))
		self.append_stops_and_stop_times(self.routes_counter, route)
		if route.frequencies:
			self.frequencies.extend(self.create_frequencies(self.routes_counter, route))
		self.append_shapes(self.routes_counter, route)
	
	def trip_headsign(self, route):
		return route.stops.tail(1).iloc(0)[0]["stop_name"]
   
	def create_route(self, route_id, route):
		return GtfsRoute(route.agency, route_id, route.name, route.route_type, route.url, route.number)
		
	def create_frequencies(self, trip_id, route):
		return [GtfsFrequency(trip_id, frequency["start_time"], frequency["end_time"], frequency["headway_secs"], self.FREQUENCY_EXACT_TIMES_NO)
			for frequency in route.frequencies]
	
	def create_calendar(self, service_id, trip):
		feed_start_date = datetime.today()
		stop_date = self.convert_stop_date(feed_start_date)
		return GtfsCalendar(service_id, stop_date, self.convert_stop_date(feed_start_date + timedelta(days=31)), *(trip.weekdays))
	
	def create_calendar_date(self, service_id, trip):
		return GtfsCalendarDate(service_id, self.convert_stop_date(trip.start), self.CALENDAR_DATES_EXCEPTION_TYPE_ADDED)
	
	def create_trip(self, route_trip_service_id, trip_headsign):
		return GtfsTrip(route_trip_service_id, route_trip_service_id, route_trip_service_id, route_trip_service_id, trip_headsign, self.NO_BIKES_ALLOWED)
	
	def convert_stop(self, stop):
		"""
		Converts a stop represented as pandas row to a gtfs stop.
		Expected attributes of stop: stop_name, stop_lon, stop_lat (in wgs84)
		"""
		self.stops_counter += 1
		id = "stop-{}".format(self.stops_counter)
		return GtfsStop(id, stop.stop_lat, stop.stop_lon, stop.stop_name)
		
	def append_stops_and_stop_times(self, trip_id, trip):
		# Assumptions: 
		# arrival_time = departure_time
		# pickup_type, drop_off_type for origin: = regularly/none
		# pickup_type, drop_off_type for destination: = none/regularly
		# timepoint = approximate for origin and destination (not sure what consequences this might have for trip planners)
		number_of_stops = len(trip.stops.index)
		total_distance = trip.stops.iloc[number_of_stops-1]["distance"]
		
		for i in range(0, number_of_stops):
			current_stop = trip.stops.iloc[i]
			if i == 0:
				first_stop_time = GtfsTimeDelta(hours = trip.start_time.hour, minutes = trip.start_time.minute, seconds = trip.start_time.second) 
				trip_time = GtfsTimeDelta()
				pickup_type = self.STOP_TIMES_STOP_TYPE_REGULARLY
				dropoff_type = self.STOP_TIMES_STOP_TYPE_NONE
			elif i == number_of_stops-1:
				trip_time = timedelta(milliseconds=int(current_stop.time))
				pickup_type = self.STOP_TIMES_STOP_TYPE_NONE
				dropoff_type = self.STOP_TIMES_STOP_TYPE_REGULARLY
			else:
				trip_time = timedelta(milliseconds=int(current_stop.time))
				is_dropoff = self.is_dropoff_stop(current_stop, total_distance)
				is_pickup = self.is_pickup_stop(current_stop, total_distance)
				pickup_type = self.STOP_TIMES_STOP_TYPE_REGULARLY if is_pickup else self.STOP_TIMES_STOP_TYPE_NONE
				dropoff_type = self.STOP_TIMES_STOP_TYPE_REGULARLY if is_dropoff else self.STOP_TIMES_STOP_TYPE_NONE
			
			stop = self.get_or_create_stop(current_stop)
			next_stop_time = first_stop_time + trip_time
			self.stop_times.append(GtfsStopTime(trip_id, str(next_stop_time), str(next_stop_time), stop.stop_id, i+1, pickup_type, dropoff_type, self.STOP_TIMES_TIMEPOINT_APPROXIMATE))
	
	def is_dropoff_stop(self, current_stop, total_distance):
		return True
		
	def is_pickup_stop(self, current_stop, total_distance):
		return True
   
	def append_shapes(self, route_id, trip):
		counter = 0
		for point in trip.geometry.coords:
				counter += 1
				self.shapes.append(GtfsShape(route_id, point[1], point[0], counter))
			
	def stop_hash(self, stop):
		return "{}#{}#{}".format(stop.stop_name,stop.stop_lat,stop.stop_lon)
		
	def get_or_create_stop(self, stop):
		gtfsstop = self.stops.get(self.stop_hash(stop))
		if gtfsstop is None:
			gtfsstop = self.convert_stop(stop)
			self.stops[self.stop_hash(stop)] = gtfsstop
		return gtfsstop
			
	def convert_stop_date(self, date_time):
		return date_time.strftime("%Y%m%d")
		
	def convert_stop_time(self, date_time):
		return date_time.strftime("%H:%M:%S")
	
	def write_csvfile(self, gtfsfolder, filename, content):
		if content:
			with open(gtfsfolder+"/"+filename, 'w', newline="\n", encoding="utf-8") as csvfile:
				self.write_csv(csvfile, content)
	
	def write_csv(self, csvfile, content):
		if hasattr(content, '_fields'):
			writer = csv.DictWriter(csvfile, content._fields)
			writer.writeheader()
			writer.writerow(content._asdict())
		else:
			if content:
				writer = csv.DictWriter(csvfile, next(iter(content))._fields)
				writer.writeheader()
				for record in content:
					writer.writerow(record._asdict())

class GtfsTimeDelta(timedelta):
	def __str__(self):
		seconds = self.total_seconds()
		hours = seconds // 3600
		minutes = (seconds % 3600) // 60
		seconds = seconds % 60
		str = '{:02d}:{:02d}:{:02d}'.format(int(hours), int(minutes), int(seconds))
		return (str)
		
	def __add__(self, other):
		if isinstance(other, timedelta):
			return self.__class__(self.days + other.days,
								  self.seconds + other.seconds,
								  self.microseconds + other.microseconds)
		return NotImplemented
	