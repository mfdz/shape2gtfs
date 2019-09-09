#Shape2GTFS

This project converts a public transit route described via two shape files (one describing the route geometry, another describing the stops along the way) into a GTFS feed.

Currently it is nothing mre than a proof of concept to illustrate how such a conversion could be done.

The arrival time is derived from the distance between two subsequent stops, assuming a fixed travel speed, which does not change according to time of day, which will not be the case in reality.

## Prerequisites
You'll need python3 installed and for each route/direction one shape file and an equally named file with an additional prefix (like e.g. "Paradas_") which contains the stop locations.

### Expected shape file formats
#### Routes file (e.g. SanPedro_Achumani.shp)

| Column | Description |
+ ------ + ----------- +
| Name   | Route long name like e.g. "San Pedro - Achumani"|
| Distancia | name does not matter, not evaluated | 
| Num_Rut | Route short name (name does not matter of field does not matter) |
| Sentido | name does not matter, not evaluated | 

#### stops file (e.g. Paradas_SanPedro_Achumani.shp)

| Column | Description |
+ ------ + ----------- +
| Name   | Stop name like e.g. "San Pedro" |
| Lat | Latitude of stop| 
| Long | Longitude of stop|
| ... | Further columns are not evaluated| 

## How to run

```
pip install -r requirements
python3 shape2gtfs/shape2gtfs.py <dir containing shape files> <prefix of stop shape file>
``` 