"""Pipeline complet : bronze -> silver -> gold -> figures + export CSV.

    docker compose run --rm spark python -m spark_jobs.pipeline
"""
from spark_jobs import bronze_to_silver, export_csv, silver_to_gold
from viz import figures

if __name__ == "__main__":
    bronze_to_silver.main()
    silver_to_gold.main()
    figures.main()
    export_csv.main()
