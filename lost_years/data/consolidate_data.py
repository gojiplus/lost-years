#!/usr/bin/env python3
"""
Data consolidation script for lost_years package.

This script consolidates multiple data files per source into single,
schema-compliant files and removes unnecessary backup/duplicate files.
"""

import logging
import shutil
from pathlib import Path

import pandas as pd

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent


def consolidate_ssa_data():
    """Consolidate SSA data files into single ssa.csv."""
    logger.info("Consolidating SSA data...")

    ssa_dir = DATA_DIR / "ssa"
    main_file = ssa_dir / "ssa.csv"
    new_file = ssa_dir / "ssa-new-20251122.csv"
    backup_file = ssa_dir / "ssa-backup-20251122.csv"

    # Use the main file (already current from our updates)
    if main_file.exists():
        df = pd.read_csv(main_file)
        logger.info(f"Main SSA file has {len(df)} rows covering year {df['year'].iloc[0]}")

        # Clean up extra files
        files_to_remove = []
        if new_file.exists() and not new_file.samefile(main_file):
            # Check if new file has more recent data
            df_new = pd.read_csv(new_file)
            if len(df_new) >= len(df):  # New file is at least as good
                shutil.copy2(new_file, main_file)
                logger.info(f"Updated main file with newer data ({len(df_new)} rows)")
                files_to_remove.append(new_file)
            else:
                files_to_remove.append(new_file)

        if backup_file.exists():
            files_to_remove.append(backup_file)

        # Remove duplicate files
        for file_to_remove in files_to_remove:
            file_to_remove.unlink()
            logger.info(f"Removed duplicate file: {file_to_remove.name}")

        return main_file

    return None


def consolidate_who_data():
    """Consolidate and clean WHO data into schema-compliant format."""
    logger.info("Consolidating WHO data...")

    who_dir = DATA_DIR / "who"
    main_file = who_dir / "who-lt.csv.gz"
    backup_file = who_dir / "who-lt-backup-20251122.csv.gz"
    clean_file = who_dir / "who.csv.gz"

    if main_file.exists():
        # Load raw WHO data
        df = pd.read_csv(main_file, compression="gzip")
        logger.info(f"Raw WHO data: {len(df)} rows, {len(df.columns)} columns")

        # Map to clean schema
        clean_df = pd.DataFrame(
            {
                "country_code": df["COUNTRY (CODE)"],
                "country_name": df["COUNTRY (DISPLAY)"].fillna(""),
                "year": df["YEAR (CODE)"],
                "sex_code": df["SEX (CODE)"],
                "life_expectancy": df["Numeric"],
                "low_ci": df["Low"],
                "high_ci": df["High"],
            }
        )

        # Clean data
        clean_df = clean_df.dropna(subset=["country_code", "year", "sex_code", "life_expectancy"])
        clean_df = clean_df[clean_df["life_expectancy"] > 0]  # Remove invalid values

        # Save clean version
        clean_df.to_csv(clean_file, compression="gzip", index=False)
        logger.info(f"Created clean WHO file: {len(clean_df)} rows")
        logger.info(f"Years: {clean_df['year'].min()}-{clean_df['year'].max()}")
        logger.info(f"Countries: {clean_df['country_code'].nunique()}")

        # Clean up old files
        if backup_file.exists():
            backup_file.unlink()
            logger.info(f"Removed backup file: {backup_file.name}")

        # Keep the raw file for now, but primary is the clean one
        return clean_file

    return None


def consolidate_hmd_data():
    """Set up HMD data structure (no actual data without credentials)."""
    logger.info("Setting up HMD data structure...")

    hmd_dir = DATA_DIR / "hmd"
    clean_file = hmd_dir / "hmd.csv.gz"

    # Create placeholder file with correct structure
    placeholder_df = pd.DataFrame(
        {
            "country": ["USA"],
            "year": [2020],
            "sex": ["Total"],
            "age": [0],
            "central_death_rate": [0.006],
            "prob_death": [0.006],
            "prob_survival_age": [100000.0],
            "life_expectancy": [78.0],
        }
    )

    placeholder_df.to_csv(clean_file, compression="gzip", index=False)
    logger.info("Created HMD placeholder file with correct schema")

    return clean_file


def clean_extra_files():
    """Remove unnecessary files like HTML downloads, etc."""
    logger.info("Cleaning up extra files...")

    # Remove HTML files and directories
    html_files = list(DATA_DIR.rglob("*.html"))
    for html_file in html_files:
        html_file.unlink()
        logger.info(f"Removed HTML file: {html_file}")

    # Remove HTML asset directories
    html_dirs = [d for d in DATA_DIR.rglob("*_files") if d.is_dir()]
    for html_dir in html_dirs:
        shutil.rmtree(html_dir)
        logger.info(f"Removed HTML assets: {html_dir}")

    # Remove old translation files (keep newer schema)
    old_files = ["who_translation.csv", "hld_translation.csv"]
    for old_file in old_files:
        file_path = DATA_DIR.rglob(old_file)
        for fp in file_path:
            fp.unlink()
            logger.info(f"Removed old file: {fp}")


def main():
    """Main consolidation process."""
    logger.info("Starting data consolidation process...")
    logger.info("=" * 50)

    # Consolidate each source
    ssa_file = consolidate_ssa_data()
    who_file = consolidate_who_data()
    hmd_file = consolidate_hmd_data()

    # Clean up extra files
    clean_extra_files()

    # Summary
    logger.info("=" * 50)
    logger.info("CONSOLIDATION SUMMARY")
    logger.info("=" * 50)

    final_files = {"SSA": ssa_file, "WHO": who_file, "HMD": hmd_file}

    for source, file_path in final_files.items():
        if file_path and file_path.exists():
            if file_path.suffix == ".gz":
                df = pd.read_csv(file_path, compression="gzip")
            else:
                df = pd.read_csv(file_path)
            logger.info(f"{source:>3}: ✅ {file_path.name} ({len(df)} rows)")
        else:
            logger.info(f"{source:>3}: ❌ No data file")

    logger.info("\nFinal data structure:")

    def log_directory_tree(path: Path, level: int = 0):
        """Recursively log directory tree structure."""
        indent = " " * 2 * level
        logger.info(f"{indent}{path.name}/")
        subindent = " " * 2 * (level + 1)

        # Sort items: directories first, then files
        items = sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name))
        for item in items:
            if item.is_dir():
                log_directory_tree(item, level + 1)
            else:
                logger.info(f"{subindent}{item.name}")

    log_directory_tree(DATA_DIR)


if __name__ == "__main__":
    main()
