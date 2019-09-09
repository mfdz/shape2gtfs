"""
Convert Shape files into GTFS
"""
import datetime
import fnmatch
import geopandas as gpd
import logging
import os
import os.path
import pyproj
import re
import shapely.wkb
import sys

from gtfs_export import GtfsExport, GtfsAgency, GtfsFeedInfo
from functools import partial
from pyproj import Proj
from shapely.geometry import *
from shapely.ops import transform


class Config:
	AGENCY_ID = 'LaPazBus'
	AGENCY = GtfsAgency('LaPazBus','La Paz Bus','http://www.lapazbus.bo/','agency_timezone','agency_lang','agency_email')
	DEFAULT_SPEED_METER_PER_SECOND = 5 # 18kmph
	SRS = pyproj.Proj(init='epsg:32719')
	HEADWAY_SECS = 10 * 60 # every 10 Minutes
	SERVICE_START_TIME = "06:00"
	SERVICE_END_TIME = "22:00"
	ROUTE_TYPE = 700
	FREQUENCIES = [{
		"start_time": "00:00",
		"end_time": "04:00",
		"headway_secs": 30 * 60 
	}, {
		"start_time": "04:00",
		"end_time": "11:00",
		"headway_secs": 10 * 60 
	}, {
		"start_time": "11:00",
		"end_time": "13:00",
		"headway_secs": 5 * 60 
	}, {
		"start_time": "13:00",
		"end_time": "17:00",
		"headway_secs": 10 * 60 
	}, {
		"start_time": "17:00",
		"end_time": "23:00",
		"headway_secs": 5 * 60 
	}, {
		"start_time": "23:00",
		"end_time": "00:00",
		"headway_secs": 30 * 60 
	}]

class Route:
	def __init__(self, name, number, stops, geometry):
		self.stops = stops
		self.name = name
		self.number = number
		self.agency = Config.AGENCY_ID
		self.url = None
		self.weekdays = [1,1,1,1,1,1,1]
		self.runs_regularly = True
		self.start_time = datetime.time(6,0,0)
		self.geometry = geometry
		self.frequencies = Config.FREQUENCIES
		self.route_type = Config.ROUTE_TYPE

class Shape2GTFS:
	
	def __init__(self, dataDir, stopsPrefix):
		self.dataDir = dataDir
		self.stopsPrefix = stopsPrefix
		self.gtfsExporter = GtfsExport([Config.AGENCY], 
			GtfsFeedInfo('feed_id','feed_publisher_name','feed_publisher_url','feed_lang','feed_version'), None)
		self.projection = project = partial(
				pyproj.transform,
				Config.SRS,
				pyproj.Proj(init='epsg:4326'))

	def read_stops(self, stopsFile):
		stops = gpd.read_file(stopsFile)
		stops = stops.rename(str.lower, axis='columns')
		stops = stops.rename(columns={"name": "stop_name", "lat": "stop_lat", "long": "stop_lon"})
		return stops

	def read_routes(self, linesFile):
		return gpd.read_file(linesFile)

	def transform_route(self, subdir, file, stopsPrefix):
		routes = self.read_routes(os.path.join(subdir, file))
		
		stops = self.read_stops(os.path.join(subdir, stopsPrefix+file))
		for index, route in routes.iterrows():
			stops['distance'] = stops.apply(lambda row: route[4].project(row['geometry']), axis=1)
			stops.sort_values('distance', inplace=True)
			stops['time'] = stops.apply(lambda row: row['distance'] / Config.DEFAULT_SPEED_METER_PER_SECOND * 1000, axis=1)
			wgs84Geometry = transform(self.projection,
				shapely.wkb.loads(
					shapely.wkb.dumps(route[4], output_dimension=2))) 
			self.gtfsExporter.convert_route(Route(route[0], route[2], stops, wgs84Geometry))
		
	def apply_to_files(self, dataDir, stopsPrefix, function):
		excludes = [stopsPrefix+"*.*"]
		includes = ['*.shp']
		# transform glob patterns to regular expressions
		includes = r'|'.join([fnmatch.translate(x) for x in includes])
		excludes = r'|'.join([fnmatch.translate(x) for x in excludes]) or r'$.'

		for subdir, dirs, files in os.walk(dataDir):
			
			# exclude/include files
			files = [f for f in files if not re.match(excludes, f)]
			files = [f for f in files if re.match(includes, f)]
			for file in files:
				function(subdir, file, stopsPrefix)

	def transform(self):
		self.apply_to_files(self.dataDir, self.stopsPrefix, self.transform_route)

		self.gtfsExporter.export('{}.zip'.format(Config.AGENCY_ID), 'out')


def main(dataDir, stopsPrefix):
	logging.basicConfig(level=logging.INFO)

	Shape2GTFS(dataDir, stopsPrefix).transform()
	
	return 0

if __name__ == '__main__':
	if len(sys.argv) != 3:
		print("Usage: python3 %s <data-dir> <stops-prefix>" % sys.argv[0])
		sys.exit(-1)

	exit(main(sys.argv[1], sys.argv[2]))