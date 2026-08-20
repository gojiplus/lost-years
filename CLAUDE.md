# Lost Years Data Update Notes

## WHO Data Source Issues & Solutions

### Country Name Mapping Issue - RESOLVED ✅
**Date Discovered:** 2025-12-27  
**Date Resolved:** 2025-12-27  
**Issue:** The WHO GHO API (https://ghoapi.azureedge.net/api/WHOSIS_000001) doesn't provide actual country names directly. The `ParentLocation` field contains WHO regions (Europe, Africa, Americas, etc.) instead of individual country names.

**Technical Details:**
- `SpatialDim` contains 3-letter ISO country codes (USA, GBR, FRA, etc.)
- `ParentLocation` contains WHO regional groupings, not country names
- Data structure: ~12,540 country records + ~396 regional/global aggregates
- Years covered: 2000-2021
- Countries covered: 196 unique country codes

**Solution Implemented:** 
- Created comprehensive ISO-3166 country code mapping (250 countries) using REST Countries API
- Saved mapping to `/lost_years/data/who/iso_country_mapping.json`
- Enhanced WHO updater to load and use country mapping automatically
- Added robust error handling and retry logic

**Current Status:** ✅ RESOLVED - WHO updater now produces proper country names and works perfectly with lost_years_who function.

## SSA Data Source Notes
- The table is the Actuarial Life Table at
  `https://www.ssa.gov/oact/STATS/table4c6.html`, not the
  `HistEst/PerLifeTables/{year}/PerLifeTables{year}.html` landing page, which
  holds no table at all -- only links to per-sex CSVs of the 1900-onwards
  historical series.
- ssa.gov's edge answers many automated clients with HTTP 403 regardless of
  headers, so `lost_years update --source ssa` may be refused; `--from-file`
  builds from a page saved in a browser.
- Shipped release: 2022. Selenium is gone; the parse is `pandas.read_html`.

## HLD Data Source Notes
- **Downloads fine with a plain GET.** The long-standing "manual download only"
  note came from issuing `HEAD`, which lifetable.de answers with 405 while
  answering `GET` with 200. `lost_years update --source hld` fetches it.
- ~56 MB zip holding one bare CSV named `res`, 21 columns, ~2.3M rows.
- Most comprehensive international dataset; not redistributed, because
  lifetable.de asks that users download their own copy.

## WHO Data Update Success Summary

### What Was Accomplished (2025-12-27)
✅ **Enhanced WHO Data Updater** - Added robust error handling, retry logic, and comprehensive logging  
✅ **ISO Country Mapping** - Created permanent mapping file for 250+ countries  
✅ **Improved Data Quality** - Country names now show actual countries instead of WHO regions  
✅ **API Robustness** - Multiple fallback endpoints and rate limiting  
✅ **Integration Tested** - Verified compatibility with lost_years_who function  
✅ **Data Currency** - Updated to latest available WHO data (2000-2021)  

### Key Files Modified/Created:
- `/lost_years/data/who/update_who_data.py` - Enhanced with retry logic and country mapping
- `/lost_years/data/who/iso_country_mapping.json` - Permanent country code mapping (250 countries)
- `/lost_years/data/who/who.csv.gz` - Updated data with proper country names

### Usage Notes:
- WHO data now covers 196 countries with proper names (not regional groupings)
- `lost_years_who()` function expects country codes (e.g., 'USA') not full names (e.g., 'United States')
- Data includes confidence intervals (low_ci, high_ci) for all life expectancy values
- Sex codes: 'MLE' (Male), 'FMLE' (Female), 'BTSX' (Both sexes)

---
*This file tracks data source issues and solutions to avoid re-discovering the same problems*