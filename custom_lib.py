import ee
from datetime import datetime, timedelta
import geemap

# Helper function to get days in month
def get_days_in_month(year, month):
    if month in [1, 3, 5, 7, 8, 10, 12]:
        return 31
    elif month in [4, 6, 9, 11]:
        return 30
    else:  # February
        if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0):
            return 29
        else:
            return 28

# Function to get the study area based on geo location
def study_location (geo_location, satellite_model, selected_date, cloud_coverage, zoomed_var):

    # translate the geo_location into an Earth Engine geometry
    study_area = ee.Geometry.Polygon(geo_location)
    
    # Mapping to into GEE Format 
    geomap = geemap.Map()

    # Center the map to the study area
    centroid_study = study_area.centroid().coordinates().getInfo()
    geomap.setCenter(centroid_study[0], centroid_study[1], zoomed_var)

    # Satellite Model for Visualization
    recent_satellite = ( 
        # Get the image collection from satellite model
        ee.ImageCollection(satellite_model)
        # Filter based on the study area
        .filterBounds(study_area)
        # Filter based on the selected date
        .filterDate(
            selected_date[0]
            , selected_date[1]
        )
        # Filter based on the cloud coverage percentage
        .filter(
            ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', cloud_coverage)
        )
        .median()
        # Select RGB bands
        .select(['B4', 'B3', 'B2']) 
    )
    
    #Visualization Parameters
    visualization_params = {
        'min': 0
        , 'max': 2000
        , 'bands': ['B4', 'B3', 'B2']
    }

    # Add the recent satellite image to the map
    geomap.addLayer(
        recent_satellite.clip(study_area)
        , visualization_params
        ,  'Satellite Image from ' + selected_date[0] + ' to ' + selected_date[1] 
    )
    print(f"\n Study area Preview")
    print(f"\n Study area coordinates: {geo_location}")
    print(f"\n Study area picture date : {selected_date[0]} to {selected_date[1]}")
    
    return geomap

# Check the SAR Availability Function
def check_sar_data_availability(geo_location, satellite_model):
    print(f"Checking ", satellite_model, "'s Data availability" )

    # Convert the geo_location 
    aoi = ee.Geometry.Polygon(geo_location)

    # Get full date range
    ic = ee.ImageCollection(satellite_model).filterBounds(aoi)
    stats = ic.reduceColumns(ee.Reducer.minMax(), ['system:time_start']).getInfo()
    
    if stats['min'] is None:
        print("No data found for this area!")
        return None
    
    start = datetime.utcfromtimestamp(stats['min']/1000)
    end = datetime.utcfromtimestamp(stats['max']/1000)
    
    # Report in the Yearly basis
    print(f"Full date range: {start.date()} to {end.date()}")
    print(f"Total years available: {(end - start).days / 365.25:.1f} years")
    
    # Check data density by year
    print("\nData Availability by Year:")
    
    yearly_stats = []
    for year in range(start.year, end.year + 1):
        year_start = f"{year}-01-01"
        year_end = f"{year}-12-31"

        year_col = (ic.filterDate(year_start, year_end).filter(ee.Filter.eq('instrumentMode', 'IW')))
        
        # Check the availability based on the polarization 
        try:
            count = year_col.size().getInfo()
            if count > 0:
                # Get polarizations available
                pols = year_col.aggregate_array('transmitterReceiverPolarisation').distinct().getInfo()
                pols_flat = [p for sublist in pols for p in sublist]
                unique_pols = list(set(pols_flat))
                
                # Get orbit directions
                orbits = year_col.aggregate_array('orbitProperties_pass').distinct().getInfo()
                
                yearly_stats.append({
                    'year': year,
                    'count': count,
                    'polarizations': unique_pols,
                    'orbits': orbits
                })
                
                print(f"{year}: {count:3d} images | Polrization Type: {unique_pols} | Orbits: {orbits}")
            else:
                print(f"{year}: No data")
        except Exception as e:
            print(f"{year}: Error checking - {e}")
    
    return yearly_stats

# Check the number of days in a month
def get_days_in_month(year, month):
    """Helper function to get the number of days in a given month and year"""
    if month == 2:  # February
        if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0):  # Leap year
            return 29
        else:
            return 28
    elif month in [4, 6, 9, 11]:  # April, June, September, November
        return 30
    else:  # January, March, May, July, August, October, December
        return 31

# Get the Optical Data Availability Function
def check_optical_data_availability(geo_location, optical_satellite_model):
    print(f"\nChecking {optical_satellite_model}'s Optical Data Availability")

    # Convert the geo_location 
    aoi = ee.Geometry.Polygon(geo_location)

    # Get full date range
    ic = ee.ImageCollection(optical_satellite_model).filterBounds(aoi)
    stats = ic.reduceColumns(ee.Reducer.minMax(), ['system:time_start']).getInfo()

    if stats['min'] is None:
        print("No data found for this area!")
        return None

    start = datetime.utcfromtimestamp(stats['min']/1000)
    end = datetime.utcfromtimestamp(stats['max']/1000)

    # Report in the Yearly basis
    print(f"Full date range: {start.date()} to {end.date()}")
    print(f"Total years available: {(end - start).days / 365.25:.1f} years")

    # Cloud Coverage Analysis
    print("\nCloud Coverage Analysis:")
    cloud_thresholds = [10, 20, 30, 50]
    for threshold in cloud_thresholds:
        clear_col = ic.filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', threshold))
        count = clear_col.size().getInfo()
        print(f"Images with <{threshold}% clouds: {count}")

    # Get the total count of images with <20% clouds for verification
    total_clear_images = ic.filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20)).size().getInfo()
    
    # Check seasonal availability
    print("\nSeasonal Availability (<20% clouds):")
    
    all_years = list(range(start.year, end.year + 1))
    
    # Initialize yearly tracking
    yearly_images = {}
    yearly_summary = {}
    for year in all_years:
        yearly_summary[year] = {'dry_season': 0, 'wet_season': 0, 'total': 0}
        yearly_images[year] = {}

    # FIXED: Collect all images by year and month - FIX THE DATE BOUNDARY ISSUE
    print("Collecting all images by month")
    for year in all_years:
        yearly_images[year] = {}
        for month in range(1, 13):
            # Skip months that are completely outside the data range
            if year == start.year and month < start.month:
                continue
            if year == end.year and month > end.month:
                continue
                
            days_in_month = get_days_in_month(year, month)
            
            # CRITICAL FIX: Handle date boundaries more carefully
            if year == start.year and month == start.month:
                # Use actual start date for first month
                month_start = start.strftime('%Y-%m-%d')
                month_end = f"{year}-{month:02d}-{days_in_month:02d}"
            elif year == end.year and month == end.month:
                # Use first of month to actual end date
                month_start = f"{year}-{month:02d}-01"
                month_end = end.strftime('%Y-%m-%d')
            else:
                # Full month - FIXED: Use proper day formatting
                month_start = f"{year}-{month:02d}-01"
                month_end = f"{year}-{month:02d}-{days_in_month:02d}"
            
            try:
                # CRITICAL FIX: Use filterDate with proper end date inclusion
                # Earth Engine filterDate is start inclusive, end exclusive
                # So we need to add one day to the end date to include the last day
                if year == end.year and month == end.month:
                    # For end boundary, use the actual end date + 1 day
                    end_date_plus_one = (end + timedelta(days=1)).strftime('%Y-%m-%d')
                    month_col = (ic.filterDate(month_start, end_date_plus_one)
                            .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20)))
                else:
                    # For normal months, add one day to include the last day
                    end_date_obj = datetime.strptime(month_end, '%Y-%m-%d')
                    end_date_plus_one = (end_date_obj + timedelta(days=1)).strftime('%Y-%m-%d')
                    month_col = (ic.filterDate(month_start, end_date_plus_one)
                            .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20)))
                
                month_count = month_col.size().getInfo()
                yearly_images[year][month] = month_count
                
                # Debug months with images
                if month_count > 0:
                    if (year == start.year and month == start.month) or (year == end.year and month == end.month):
                        print(f"   Partial month {month_start} to {month_end}: {month_count} images")
                    else:
                        print(f"   Full month {month_start} to {month_end}: {month_count} images")
                        
            except Exception as e:
                print(f"Error processing {month_start} to {month_end}: {e}")
                yearly_images[year][month] = 0

    # Now assign images to seasons
    # DRY SEASON (May-Oct) - months 5,6,7,8,9,10
    print(f"\nDry Season (May-Oct):")
    dry_season_total = 0
    dry_months = [5, 6, 7, 8, 9, 10]

    for year in all_years:
        seasonal_count = 0
        for month in dry_months:
            if month in yearly_images[year]:
                seasonal_count += yearly_images[year][month]
        
        yearly_summary[year]['dry_season'] = seasonal_count
        print(f"{year}: {seasonal_count} clear images")
        dry_season_total += seasonal_count
    
    print(f"Total for Dry Season (May-Oct): {dry_season_total} images")
    
    # WET SEASON (Nov-Apr) - FIXED logic
    print(f"\nWet Season (Nov-Apr):")
    wet_season_total = 0
    
    for year in all_years:
        seasonal_count = 0
        
        # November-December of current year (months 11, 12)
        for month in [11, 12]:
            if month in yearly_images[year]:
                seasonal_count += yearly_images[year][month]
        
        # January-April of NEXT year (months 1, 2, 3, 4) - but assign to current wet season
        next_year = year + 1
        if next_year in yearly_images:  # Only if next year exists in our data
            for month in [1, 2, 3, 4]:
                if month in yearly_images[next_year]:
                    seasonal_count += yearly_images[next_year][month]
        
        yearly_summary[year]['wet_season'] = seasonal_count
        print(f"{year}: {seasonal_count} clear images")
        wet_season_total += seasonal_count
    
    print(f"Total for Wet Season (Nov-Apr): {wet_season_total} images")
    
    # Calculate yearly totals and verify
    total_accounted = 0
    
    print(f"\n DETAILED YEAR-BY-YEAR BREAKDOWN:")
    for year in all_years:
        # For yearly total, count ALL months in this calendar year
        year_total = 0
        month_details = []
        
        for month in range(1, 13):
            if month in yearly_images[year]:
                month_count = yearly_images[year][month]
                year_total += month_count
                if month_count > 0:
                    month_details.append(f"M{month}:{month_count}")
        
        yearly_summary[year]['total'] = year_total
        total_accounted += year_total
        
        # if month_details:
        #     print(f" {year}: {year_total} total ({', '.join(month_details)})")
        # else:
        #     print(f" {year}: {year_total} total")
    
    # Verification
    # print(f"\n VERIFICATION:")
    # print(f"   Total images with <20% clouds (direct count): {total_clear_images}")
    # print(f"   Total accounted for in yearly breakdown: {total_accounted}")
    
    # if total_clear_images != total_accounted:
    #     print(f" MISMATCH: {total_clear_images - total_accounted} images unaccounted")
    #     print(f" (This was due to Earth Engine filterDate being end-exclusive)")
    # else:
    #     print(f" All images accounted for!")
    
    # # YEARLY SUMMARY
    print(f"\n{'='*60}")
    print(f"YEARLY SUMMARY (<20% clouds)")
    print(f"{'='*60}")
    print(f"{'Year':<6} {'Dry Season':<12} {'Wet Season':<12} {'Total':<8}")
    print(f"{'-'*40}")
    
    for year in sorted(yearly_summary.keys()):
        dry = yearly_summary[year]['dry_season']
        wet = yearly_summary[year]['wet_season']
        total = yearly_summary[year]['total']
        print(f"{year:<6} {dry:<12} {wet:<12} {total:<8}")
    
    # print(f"{'-'*40}")
    # print(f"{'TOTAL':<6} {dry_season_total:<12} {wet_season_total:<12} {total_accounted:<8}")
    
    # FINAL STATISTICS
    # print(f"\n FINAL STATISTICS:")
    # print(f"Total clear images (<20% clouds): {total_clear_images}")
    # print(f"Dry season images (May-Oct): {dry_season_total}")
    # print(f"Wet season images (Nov-Apr): {wet_season_total}")
    # print(f"Average images per year: {total_clear_images/len(all_years):.1f}")
    # print(f"Years analyzed: {len(all_years)}")
    
    # # Note about seasonal vs yearly totals
    # seasonal_total = dry_season_total + wet_season_total
    # if seasonal_total != total_accounted:
    #     print(f"\n NOTE:")
    #     print(f"Seasonal total ({seasonal_total}) ≠ Yearly total ({total_accounted})")
    #     print(f"This is expected because wet season spans two calendar years")
    #     print(f"Jan-Apr images are counted in both wet season and yearly totals")
    
    # Create structured return data
    yearly_optical_stats = []
    for year in sorted(yearly_summary.keys()):
        yearly_optical_stats.append({
            'year': year,
            'dry_season_count': yearly_summary[year]['dry_season'],
            'wet_season_count': yearly_summary[year]['wet_season'],
            'count': yearly_summary[year]['total']
        })
    
    return yearly_optical_stats

def setting_up_analysis_periods ( sar_yearly_stats, optical_yearly_stats ) :
    print("\nSetting up Analysis Periods based on SAR Data Availability")

    # Check if SAR data is available
    if not sar_yearly_stats:
        print(" No SAR data available for analysis setup")
        return None

    # Find years with good data coverage (at least 50 images per year for high quality analysis)
    good_years = [year for year in sar_yearly_stats if year['count'] >= 50]
    
    # If less than 2 good years, relax criteria to at least 20 images per year
    if len(good_years) < 2:
        print("Limited data for temporal analysis, using available years")
        good_years = sorted(sar_yearly_stats, key=lambda x: x['count'], reverse=True)[:2]

    # Sort by year
    good_years = sorted(good_years, key=lambda x: x['year'])

    # Setting up the Base Years
    baseline_year = None 
    current_year = None
    intermediate_year = None

    # use the earliest available 
    if baseline_year is None:
        baseline_year = good_years[0]

    # If no recent year, use the latest available
    if current_year is None:
        current_year = good_years[-1]

    # If no intermediate year, use the year before the current year
    if intermediate_year is None:
        intermediate_year = good_years[-2] if len(good_years) > 1 else None

    return baseline_year, intermediate_year, current_year