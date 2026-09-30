import csv
from decimal import Decimal
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from routing.geocoding import lookup_city
from routing.models import Station
from routing.stations import reset_index

US_STATES = set(
    "AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK "
    "OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split()
)


class Command(BaseCommand):
    help = "Load the OPIS fuel price CSV: keep US stops, de-dupe by OPIS id (lowest price), geocode city offline."

    def add_arguments(self, parser):
        parser.add_argument("csv_path", nargs="?", default=str(Path(settings.BASE_DIR) / "data" / "fuel-prices.csv"))

    def handle(self, *args, csv_path, **opts):
        path = Path(csv_path)
        if not path.exists():
            raise CommandError(f"{path} not found")

        best, skipped_non_us = {}, 0
        with path.open(newline="", encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                if row["State"].strip().upper() not in US_STATES:
                    skipped_non_us += 1
                    continue
                oid, price = int(row["OPIS Truckstop ID"]), Decimal(row["Retail Price"])
                if oid not in best or price < best[oid][1]:
                    best[oid] = (row, price)

        stations, unmatched = [], []
        for oid, (row, price) in best.items():
            city, state = row["City"].strip(), row["State"].strip().upper()
            pt = lookup_city(city, state)
            if pt is None:
                unmatched.append(f"{city}, {state}")
                continue
            stations.append(Station(opis_id=oid, name=row["Truckstop Name"].strip(), address=row["Address"].strip(),
                                    city=city, state=state, price=price, lat=pt[0], lon=pt[1]))

        with transaction.atomic():
            Station.objects.all().delete()
            Station.objects.bulk_create(stations, batch_size=1000)
        reset_index()
        self.stdout.write(self.style.SUCCESS(
            f"Imported {len(stations)} stations ({skipped_non_us} non-US rows skipped, {len(unmatched)} ungeocodable)."))
        if unmatched:
            self.stdout.write("Unmatched: " + "; ".join(sorted(set(unmatched))[:20]))
