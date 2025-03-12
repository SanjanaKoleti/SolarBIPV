import os
import pvlib
import pandas as pd
from datetime import datetime
from shapely.geometry import Polygon, MultiPolygon
import shapely.affinity
import numpy as np
from shapely.ops import unary_union
from shapely import wkt
import geopandas as gpd
from pyproj import Transformer

# (Ahmedabad) in EPSG:32643 coordinates
utm_x = 253189
utm_y = 2547297

date_time = datetime.now()

# EPSG:32643 to EPSG:4326
transformer_to_latlon = Transformer.from_crs("EPSG:32643", "EPSG:4326", always_xy=True)

# UTM coordinates to Latitude and Longitude 
latitude, longitude = transformer_to_latlon.transform(utm_x, utm_y)


location = pvlib.location.Location(latitude, longitude)

# Getting the solar position for the given time
times = pd.DatetimeIndex([date_time])
solar_position = location.get_solarposition(times)

# Extracting solar elevation and azimuth
solar_elevation = solar_position['elevation'].values[0]
solar_azimuth = solar_position['azimuth'].values[0]

print(f"Solar Elevation: {solar_elevation:.2f} degrees")
print(f"Solar Azimuth: {solar_azimuth:.2f} degrees")

# GHI values (kWh/day/m²) for different seasons
ghi_values = {'Spring': 7.47, 'Summer': 5.50, 'Autumn': 5.06, 'Winter': 4.94}

# Determining GHI based on the current month
month = date_time.month
if 3 <= month <= 5:
    ghi_value = ghi_values['Spring']
elif 6 <= month <= 8:
    ghi_value = ghi_values['Summer']
elif 9 <= month <= 11:
    ghi_value = ghi_values['Autumn']
else:
    ghi_value = ghi_values['Winter']

# sahdow calculation
def calculate_shadow(building_polygon, building_height, sun_azimuth, sun_elevation):
    if isinstance(building_polygon, (Polygon, MultiPolygon)):
        shadow_length = building_height / np.tan(np.radians(sun_elevation))
        dx = shadow_length * np.cos(np.radians(sun_azimuth))
        dy = shadow_length * np.sin(np.radians(sun_azimuth))
        return [shapely.affinity.translate(poly, xoff=dx, yoff=dy) for poly in building_polygon.geoms] if isinstance(building_polygon, MultiPolygon) else [shapely.affinity.translate(building_polygon, xoff=dx, yoff=dy)]
    return None

# lateral surface area calculation
def calculate_lateral_surface_area(building_polygon, building_height):
    return building_polygon.length * building_height if building_polygon.is_valid else 0

# exposed area calculation
def calculate_exposed_area(building_polygon, shadows, building_height):
    roof_area = building_polygon.area
    lateral_surface_area = calculate_lateral_surface_area(building_polygon, building_height)
    shadow_union = unary_union(shadows) if shadows else None
    return roof_area + lateral_surface_area - (shadow_union.area if shadow_union else 0)

# solar energy potential calculation
def calculate_solar_potential(exposed_area, ghi_value):
    efficiency=0.2
    return exposed_area * ghi_value * efficiency
# Load building data
file_path = 'building_data.csv'  
lod1_data = pd.read_csv(file_path)


lod1_data['geometry'] = lod1_data['geometry'].apply(wkt.loads)

transformer = Transformer.from_crs("EPSG:32643", "EPSG:4326", always_xy=True)

# to transform geometries
def transform_geometry(geom):
    if isinstance(geom, Polygon):
        return Polygon([transformer.transform(x, y) for x, y in geom.exterior.coords])
    elif isinstance(geom, MultiPolygon):
        return MultiPolygon([Polygon([transformer.transform(x, y) for x, y in poly.exterior.coords]) for poly in geom.geoms])
    return None

# calculate no.of panels and cost of panels
def calculate_panels_and_cost(exposed_area, panel_area=1.99, cost_per_panel=12000):
    num_panels = exposed_area // panel_area
    total_cost = num_panels * cost_per_panel
    return num_panels, total_cost

# Transform coordinates and calculating result
results = []
for i, (building_geom, building_height) in enumerate(lod1_data[['geometry', 'height']].values):
    building_geom = transform_geometry(building_geom)
    building_shadows = calculate_shadow(building_geom, building_height, solar_azimuth, solar_elevation)
    exposed_area = calculate_exposed_area(building_geom, building_shadows, building_height) * 10000
    potential = calculate_solar_potential(exposed_area / 100, ghi_value) * 10
    num_panels, total_cost = calculate_panels_and_cost(exposed_area)

    results.append({
        'Building_ID': i + 1,
        'geometry': building_geom,
        'Exposed_Area': exposed_area,
        'Solar_Potential_kWh/day': potential,
        'Number_of_Panels': num_panels,
        'Installation_Cost_₹': total_cost
    })

gdf = gpd.GeoDataFrame(results, geometry='geometry', crs='EPSG:4326')

gdf = gdf.dissolve(by='Building_ID', as_index=False)
gdf['geometry'] = gdf['geometry'].apply(lambda geom: unary_union(geom) if geom else None)

gdf = gdf[gdf['geometry'].notnull()]
gdf['geometry'] = gdf['geometry'].apply(lambda geom: geom.buffer(0) if geom and not geom.is_valid else geom)

gdf.to_file('results5.geojson', driver='GeoJSON')
print("Updated GeoJSON saved as results5.geojson")
