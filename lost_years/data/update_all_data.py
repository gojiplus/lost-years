#!/usr/bin/env python3
"""Master data update script.

Updates all data sources in the lost_years package.
"""

import argparse
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Import individual updaters from their new locations in data folders

# Add the current data directory and subdirectories to Python path
data_dir = Path(__file__).parent
sys.path.insert(0, str(data_dir))

try:
    # Import from data folders - relative to current directory
    sys.path.insert(0, str(data_dir / "who"))
    from update_who_data import WHODataUpdater

    sys.path.insert(0, str(data_dir / "ssa"))
    from update_ssa_data import SSADataUpdater

    sys.path.insert(0, str(data_dir / "hld"))
    from update_hld_data import HLDDataUpdater
except ImportError as e:
    logger.error("Could not import data updaters: %s", e)
    logger.error("Update scripts should be in their respective data folders")
    sys.exit(1)


class MasterDataUpdater:
    """Master updater for all data sources."""

    def __init__(self):
        """Start an empty run, stamping the start time for the summary."""
        self.results = {}
        self.start_time = datetime.now(tz=UTC)

    def update_who_data(self):
        """Update WHO data."""
        logger.info("=" * 50)
        logger.info("UPDATING WHO DATA")
        logger.info("=" * 50)

        try:
            updater = WHODataUpdater()
            success = updater.update_who_data()
            self.results["WHO"] = {
                "success": success,
                "message": "Successfully updated WHO data"
                if success
                else "Failed to update WHO data",
            }
            return success
        except Exception as e:
            logger.error("Error updating WHO data: %s", e)
            self.results["WHO"] = {"success": False, "message": f"Error: {e}"}
            return False

    def update_ssa_data(self):
        """Update SSA data."""
        logger.info("=" * 50)
        logger.info("UPDATING SSA DATA")
        logger.info("=" * 50)

        try:
            updater = SSADataUpdater()
            success = updater.update_ssa_data()
            self.results["SSA"] = {
                "success": success,
                "message": "Successfully updated SSA data"
                if success
                else "Failed to update SSA data (website may block automated access)",
            }
            return success
        except Exception as e:
            logger.error("Error updating SSA data: %s", e)
            self.results["SSA"] = {"success": False, "message": f"Error: {e}"}
            return False

    def update_hld_data(self):
        """Update HLD data (manual download required)."""
        logger.info("=" * 50)
        logger.info("UPDATING HLD DATA")
        logger.info("=" * 50)

        try:
            updater = HLDDataUpdater()
            success = updater.update_hld_data()
            self.results["HLD"] = {
                "success": success,
                "message": "Successfully updated HLD data"
                if success
                else "Failed to update HLD data (manual download may be required)",
            }
            return success
        except Exception as e:
            logger.error("Error updating HLD data: %s", e)
            self.results["HLD"] = {"success": False, "message": f"Error: {e}"}
            return False

    def print_summary(self):
        """Print summary of update results."""
        end_time = datetime.now(tz=UTC)
        duration = end_time - self.start_time

        logger.info("=" * 60)
        logger.info("DATA UPDATE SUMMARY")
        logger.info("=" * 60)
        logger.info("Started: %s", self.start_time.strftime("%Y-%m-%d %H:%M:%S"))
        logger.info("Finished: %s", end_time.strftime("%Y-%m-%d %H:%M:%S"))
        logger.info("Duration: %s", duration)
        logger.info("")

        success_count = 0
        total_count = len(self.results)

        for source, result in self.results.items():
            status = "✅ SUCCESS" if result["success"] else "❌ FAILED"
            logger.info("%10s: %s", source, status)
            logger.info("%12s  %s", "", result["message"])
            logger.info("")

            if result["success"]:
                success_count += 1

        logger.info(
            "Overall: %s/%s data sources updated successfully",
            success_count,
            total_count,
        )

        match (success_count, total_count):
            case (s, t) if s == t:
                logger.info("🎉 All data sources updated successfully!")
            case (s, _) if s > 0:
                logger.info("⚠️  Some data sources updated successfully")
            case _:
                logger.info("💥 No data sources updated successfully")

        return success_count, total_count

    def update_all(self, sources=None):
        """Update all specified data sources."""
        logger.info("Starting master data update process...")

        # Default to all sources if none specified
        if sources is None:
            sources = ["who", "ssa", "hld"]

        sources = [s.lower() for s in sources]

        # Update each source
        if "who" in sources:
            self.update_who_data()

        if "ssa" in sources:
            self.update_ssa_data()

        if "hld" in sources:
            self.update_hld_data()

        # Print summary
        success_count, total_count = self.print_summary()

        return success_count == total_count


def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="Update all lost_years data sources")
    parser.add_argument(
        "--sources",
        nargs="*",
        choices=["who", "ssa", "hld", "all"],
        default=["all"],
        help="Data sources to update (default: all)",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    print("Lost Years Data Updater")
    print("=" * 40)
    print()
    print("This script updates data sources for the lost_years package:")
    print("• WHO: World Health Organization life expectancy data")
    print("• SSA: US Social Security Administration life tables")
    print("• HLD: Human Life-Table Database (manual download from lifetable.de)")
    print()

    # Handle 'all' in sources list
    sources = ["who", "ssa", "hld"] if "all" in args.sources else args.sources

    print(f"Updating sources: {', '.join(sources)}")
    print()

    # Special message for HLD
    if "hld" in sources:
        print("📋 HLD Update Requirements:")
        print("   • Manual download from https://www.lifetable.de/")
        print("   • Extract to data/hld/ directory")
        print()

    # Create updater and run
    updater = MasterDataUpdater()
    success = updater.update_all(sources=sources)

    if success:
        print("🎉 All requested data sources updated successfully!")
        return 0
    print("💥 Some updates failed. Check the logs above for details.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
