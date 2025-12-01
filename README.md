# 🏔️ Swiss Ecosystems

## Table of Contents
- [🌿 Context](#🌿-context)
- [⚙️ Prerequisites](#⚙️-prerequisites)
- [🚀 Usage](#🚀-usage)
   - [🐋 Container setup](#🐋-container-setup)
   - [➡️ Entry point](#➡️-entry-point)
   - [🛠️ Tools](#🛠️-tools)
- [🗺️ Visualization - interactive map](#🗺️-visualization---interactive-map)
- [📂 Project structure](#📂-project-structure)
- [📌 Additional notes](#📌-additional-notes)

## 🌿 Context

**Swiss Ecosystems** is a project for studying and mapping **Swiss ecosystems** based on geolocated fauna and flora observations.

The objective is to:
1. **Enrich observations** with official Swiss altitudes (swissALTI3D),
2. **Identify coherent ecological zones** via spatial clustering,
3. **Dynamically visualize** the ecosystems on an interactive web map.

The full pipeline goes from raw CSV observations to an interactive Leaflet map showing colored, interactive ecosystem polygons.

<br>

## ⚙️ Prerequisites

### 🐋 Docker and Docker Compose
All processing (GDAL, Python scripts) runs inside Docker containers.  
Ensure Docker is installed and working:

```bash
docker --version
docker compose version
```

<br>

## 🚀 Usage

### 🐋 Container setup

1. Clone the repository:
   ```bash
   git clone https://github.com/ProbStatFauneEtFlore/Ecosystems.git
   cd Ecosystems
   ```

2. Start the containers:
   ```bash
   docker compose up -d
   ```

   This launches:
   - **gdal_tools** -> GDAL & Python tools (`/app/tools`)
   - **shared volume** mounted at `./app`

3. Check that everything is running:
   ```bash
   docker ps
   ```

4. Run commands inside the `gdal_tools` container:
   ```bash
   docker exec -it gdal_tools bash # enter the container (base dir: /app)
   ```

---

### ➡️ Entry point
In the `gdal_tools` container, from `app/`, use the single entry point `eco_app.py` to run the different Python tools.
- Preferred shortcut: `./eco_app <tool> [options]` (shell wrapper in app, add the executable bit if needed: `chmod +x eco_app`)
- Or directly: `python3 eco_app.py <tool> [options]`

---

### 🛠️ Tools
- `filter_csv`: quality filtering of observations (GPS accuracy, altitude, etc.)
   ```bash
   python3 eco_app.py filter_csv  
         <[position|elevation|grade]>              # filter mode
         --in <input_csv>                          # optional, prefer default naming
         --out <output_csv>                        # optional, prefer default naming
         --exclude-filter <filters_to_exclude>     # excludes sources files with these filters
         --include-filter <filters_to_include>     # includes only source files with these filters
         --exclude-enrich <enrichments_to_exclude> # excludes source files with these enrichments
         --include-enrich <enrichments_to_include> # includes only source files with these enrichments
         --eps <positional_accuracy_threshold>     # used only with 'position' filter
         --types <[casual|research|needs_id]>      # used only with 'grade' filter
   ```
   
- `enrich_csv`: enrich observations with external data (taxa, altitude)
   - `enrich_csv taxa` 
      ```bash
      python3 eco_app.py enrich_csv  
            taxa                                      # enrichment mode
            --in <input_csv>                          # optional, prefer default naming
            --out <output_csv>                        # optional, prefer default naming
            --batch-size <num_rows_per_batch>         # number of rows to process per batch
            --delay <seconds_between_batches>         # delay between batches to avoid overloading services
            --exclude-filter <filters_to_exclude>     # excludes sources files with these filters
            --include-filter <filters_to_include>     # includes only source files with these filters
            --exclude-enrich <enrichments_to_exclude> # excludes source files with these enrichments
            --include-enrich <enrichments_to_include> # includes only source files with these enrichments
      ```

   - `enrich_csv elevation`
      ```bash
      python3 eco_app.py enrich_csv  
            elevation                                 # enrichment mode
            --in <input_csv>                          # optional, prefer default naming
            --out <output_csv>                        # optional, prefer default naming
            --tif-dir <directory_with_tif_tiles>      # directory containing swissALTI3D .tif tiles
            --workers <num_parallel_workers>          # number of parallel workers for speedup
            --lon-field <longitude_column_name>       # name of the longitude column in the CSV
            --lat-field <latitude_column_name>        # name of the latitude column in the CSV
            --exclude-filter <filters_to_exclude>     # excludes sources files with these filters
            --include-filter <filters_to_include>     # includes only source files with these filters
            --exclude-enrich <enrichments_to_exclude> # excludes source files with these enrichments
            --include-enrich <enrichments_to_include> # includes only source files with these enrichments
      ```

- `combine_csvs`: combine multiple observation CSVs into one
   ```bash
   python3 eco_app.py combine_csvs  
         <input_csv1> <input_csv2> ...                # list of input CSV files
         --out <output_csv>                           # optional, prefer default naming
         --id <id_column_name>                        # name of the common unique ID column
         --intersect                                  # Combines and keeps only common rows
   ```

- `import_tiles`: download swissALTI3D tiles
   ```bash
   python3 eco_app.py import_tiles  
         --force                                      # force re-download of all tiles
   ```
- `cluster_ecosystemes`: spatial clustering of observations into ecosystems
   ```bash
   python3 eco_app.py cluster_ecosystemes  
         --in <input_csv>                             # optional, prefer default naming
         --out <output_csv>                           # optional, prefer default naming
         --out-geojson-2056 <output_geojson_epsg2056> # output GeoJSON in EPSG:2056
         --out-geojson-4326 <output_geojson_epsg4326> # output GeoJSON in EPSG:4326
         --eps <neighborhood_radius_meters>           # maximum neighborhood radius (meters, EPSG:2056)
         --min-samples <min_observations_per_cluster> # minimum number of observations to form a cluster
         --alt-scale <altitude_normalization_factor>  # altitude normalization factor
         --lon-field <longitude_column_name>          # name of the longitude column in the CSV
         --lat-field <latitude_column_name>           # name of the latitude column in the CSV
         --elev-field <elevation_column_name>         # name of the elevation column in the CSV
         --year-field <year_column_name>              # name of the year column in the CSV
         --exclude-filter <filters_to_exclude>        # excludes sources files with these filters
         --include-filter <filters_to_include>        # includes only source files with these filters
         --exclude-enrich <enrichments_to_exclude>    # excludes source files with these enrichments
         --include-enrich <enrichments_to_include>    # includes only source files with these enrichments

   ```

---

### 🗺️ Visualization - interactive map

1. Start a lightweight local web server:
   ```bash
   python -m http.server 8000
   ```

2. Open in your browser:
   -> http://localhost:8000/eco_map.html

3. **Interactions**
   - Each colored polygon = one ecosystem (DBSCAN cluster)
   - Hover -> taxon list and observation counts
   - Click -> popup with taxon details

<br>

## 📂 Project structure

```
/Ecosystems
├─ 📁 app/
│  ├─ 📁 data/
│  │  ├─ 📁 clusters/
│  │  │  ├─ 📄 manifest.json
│  │  │  └─ 📁 clusters-YYYY_MM_DD-HH_MM/  # timestamped clustering outputs
│  │  ├─ 📁 old/                           # legacy processed files (kept for reference)
│  │  ├─ 📁 processed/                     # filtered/enriched CSV outputs
│  │  ├─ 📁 swissALTI3D_tiles/             # downloaded swissALTI3D .tif tiles
│  │  ├─ 📄 observations_swiss.csv         # raw observations
│  │  ├─ 📄 swissalti3d_urls.txt           # source list for swissALTI3D tiles
│  │  └─ 📄 taxa_infos.json                # cached taxa enrichment data
│  ├─ 📁 tools/
│  │  ├─ 🐍 cluster_ecosystems.py
│  │  ├─ 🐍 enrich_csv.py
│  │  ├─ 🐍 filter_csv.py
│  │  ├─ 🐍 import_tiles.py
│  │  ├─ 🐚 import_tiles.sh
│  │  └─ 🐍 utils.py
│  ├─ 🚀 eco_app                           # shell wrapper
│  ├─ 🐍 eco_app.py                        # Python entry point
│  ├─ 🌐 eco_map.html
│  └─ 🐍 __init__.py
├─ 🐋 docker-compose.yaml
├─ 🐋 Dockerfile.gdal
├─ 📄 .gitignore
├─ 📖 README.md
└─ 📄 .DS_Store
```

<br>

## 📌 Additional notes

- **DBSCAN** detects dense spatial clusters. Points with `cluster_id = -1` are isolated observations.
- **EPSG:2056 (LV95)** is used for metric computations.
- **EPSG:4326 (WGS84)** is used for web visualizations.
- Ecosystem polygons are generated as the union of circles of radius `eps` around each cluster observation.

---
