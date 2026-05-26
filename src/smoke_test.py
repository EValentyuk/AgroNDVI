import sys

sys.stdout.reconfigure(encoding="utf-8")


def main() -> None:
    import affine
    import boto3
    import folium
    import geopandas
    import lightgbm
    import matplotlib
    import numpy
    import pandas
    import plotly
    import pyproj
    import rasterio
    import shapely
    import sklearn
    import streamlit

    versions = {
        "python": sys.version.split()[0],
        "numpy": numpy.__version__,
        "pandas": pandas.__version__,
        "rasterio": rasterio.__version__,
        "GDAL (via rasterio)": rasterio.__gdal_version__,
        "geopandas": geopandas.__version__,
        "shapely": shapely.__version__,
        "pyproj": pyproj.__version__,
        "folium": folium.__version__,
        "lightgbm": lightgbm.__version__,
        "sklearn": sklearn.__version__,
        "streamlit": streamlit.__version__,
        "plotly": plotly.__version__,
        "matplotlib": matplotlib.__version__,
        "affine": affine.__version__,
        "boto3": boto3.__version__,
    }

    width = max(len(k) for k in versions) + 2
    for name, ver in versions.items():
        print(f"{name:<{width}} {ver}")


if __name__ == "__main__":
    main()
