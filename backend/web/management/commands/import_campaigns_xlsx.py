"""Import campaign data from Excel (SABESP-style extraction).

Reads the consolidated sheet (with columns: campanha, tema, veiculo,
investimento, impressoes, cliques, watches25..watches100, engajamento, etc.)
and creates PlacementLine + PlacementDay records grouped by veiculo.

Usage:
    python manage.py import_campaigns_xlsx path/to/file.xlsx --cliente-id=1
    python manage.py import_campaigns_xlsx path/to/file.xlsx --cliente-id=1 --sheet="sheet19"
    python manage.py import_campaigns_xlsx path/to/file.xlsx --cliente-id=1 --dry-run
"""

import re
import zipfile
import xml.etree.ElementTree as ET
from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from accounts.models import Cliente
from campaigns.models import Campaign, PlacementLine, PlacementDay


# Map Excel veiculo values → PlacementLine.MediaChannel values
VEICULO_MAP = {
    "meta": PlacementLine.MediaChannel.META,
    "tiktok": PlacementLine.MediaChannel.TIKTOK,
    "linkedin": PlacementLine.MediaChannel.LINKEDIN,
    "dv360": PlacementLine.MediaChannel.DV360,
    "dv360-youtube": PlacementLine.MediaChannel.DV360_YOUTUBE,
    "dv360-spotify": PlacementLine.MediaChannel.DV360_SPOTIFY,
    "dv360-eletromidia": PlacementLine.MediaChannel.DV360_ELETROMIDIA,
    "dv360-netflix": PlacementLine.MediaChannel.DV360_NETFLIX,
    "dv360-globoplay": PlacementLine.MediaChannel.DV360_GLOBOPLAY,
    "dv360-admooh": PlacementLine.MediaChannel.DV360_ADMOOH,
    # Fallbacks for existing channels
    "google": PlacementLine.MediaChannel.GOOGLE,
    "youtube": PlacementLine.MediaChannel.YOUTUBE,
    "display": PlacementLine.MediaChannel.DISPLAY,
    "search": PlacementLine.MediaChannel.SEARCH,
}


def _read_xlsx_sheet(filepath, target_sheet=None):
    """Read an xlsx sheet using only zipfile + xml (no openpyxl dependency).

    Returns (header_list, rows_as_dicts).
    """
    z = zipfile.ZipFile(filepath)
    ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

    # Shared strings
    ss_tree = ET.parse(z.open("xl/sharedStrings.xml"))
    strings = [el.text or "" for el in ss_tree.findall(".//s:t", ns)]

    # Find the right sheet
    sheet_files = sorted(
        [f for f in z.namelist() if "worksheets/sheet" in f and f.endswith(".xml")]
    )

    best_sheet = None
    best_rows = 0

    if target_sheet:
        # Match by name
        for sf in sheet_files:
            if target_sheet in sf:
                best_sheet = sf
                break
        if not best_sheet:
            raise CommandError(
                f"Sheet '{target_sheet}' not found. Available: {sheet_files}"
            )
    else:
        # Auto-detect: find the sheet with header starting with "campanha, tema, veiculo"
        for sf in sheet_files:
            tree = ET.parse(z.open(sf))
            rows = tree.findall(".//s:sheetData/s:row", ns)
            if not rows:
                continue
            # Check header
            header_vals = []
            for c in rows[0].findall("s:c", ns):
                v = c.find("s:v", ns)
                t = c.get("t", "")
                if v is not None and v.text:
                    if t == "s":
                        header_vals.append(strings[int(v.text)])
                    else:
                        header_vals.append(v.text)
            if (
                len(header_vals) >= 6
                and "campanha" in header_vals
                and "veiculo" in header_vals
                and "investimento" in header_vals
            ):
                if len(rows) > best_rows:
                    best_rows = len(rows)
                    best_sheet = sf

    if not best_sheet:
        raise CommandError(
            "Could not find a sheet with columns: campanha, tema, veiculo, investimento. "
            "Use --sheet to specify."
        )

    # Parse the sheet
    tree = ET.parse(z.open(best_sheet))
    xml_rows = tree.findall(".//s:sheetData/s:row", ns)

    def col_idx(ref):
        letters = re.match(r"([A-Z]+)", ref).group(1)
        idx = 0
        for ch in letters:
            idx = idx * 26 + (ord(ch) - ord("A") + 1)
        return idx - 1

    def cell_val(cell):
        v = cell.find("s:v", ns)
        t = cell.get("t", "")
        if v is None or v.text is None:
            return ""
        if t == "s":
            return strings[int(v.text)]
        return v.text

    # Header
    header = {}
    for c in xml_rows[0].findall("s:c", ns):
        ci = col_idx(c.get("r", "A1"))
        header[ci] = cell_val(c)

    # Data rows
    data_rows = []
    for xml_row in xml_rows[1:]:
        d = {}
        for c in xml_row.findall("s:c", ns):
            ci = col_idx(c.get("r", "A1"))
            col_name = header.get(ci, "")
            if col_name:
                d[col_name] = cell_val(c)
        # Skip empty rows
        if d.get("veiculo") or d.get("investimento"):
            data_rows.append(d)

    z.close()
    return list(header.values()), data_rows, best_sheet


class Command(BaseCommand):
    help = "Importa dados de campanhas de um Excel (formato SABESP/DV360)"

    def add_arguments(self, parser):
        parser.add_argument("filepath", type=str, help="Caminho para o arquivo .xlsx")
        parser.add_argument(
            "--cliente-id", type=int, required=True, help="ID do cliente"
        )
        parser.add_argument(
            "--sheet",
            type=str,
            default=None,
            help="Nome da sheet (ex: sheet19). Auto-detecta se omitido.",
        )
        parser.add_argument(
            "--campaign-name",
            type=str,
            default=None,
            help="Nome da campanha pai (default: auto from filename)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Mostra o que seria importado sem salvar",
        )

    def handle(self, *args, **options):
        import glob as _glob

        filepath = options["filepath"]
        cliente_id = options["cliente_id"]
        dry_run = options["dry_run"]

        # Handle unicode path issues on Windows
        if not __import__("os").path.exists(filepath):
            matches = _glob.glob(filepath)
            if not matches:
                # Try parent dir glob
                import os
                parent = os.path.dirname(filepath) or "."
                pattern = os.path.join(parent, "*.xlsx")
                matches = _glob.glob(pattern)
            if matches:
                filepath = matches[0]

        # Validate cliente
        try:
            cliente = Cliente.objects.get(id=cliente_id)
        except Cliente.DoesNotExist:
            raise CommandError(f"Cliente ID {cliente_id} nao encontrado.")

        self.stdout.write(f"Cliente: {cliente.nome}")
        self.stdout.write(f"Arquivo: {filepath!r}")

        # Read Excel
        header, rows, sheet_name = _read_xlsx_sheet(filepath, options.get("sheet"))
        self.stdout.write(f"Sheet: {sheet_name}")
        self.stdout.write(f"Colunas: {header}")
        self.stdout.write(f"Linhas com dados: {len(rows)}")

        if not rows:
            self.stdout.write(self.style.WARNING("Nenhuma linha com dados encontrada."))
            return

        # Create or get parent Campaign
        campaign_name = options.get("campaign_name") or f"Import - {cliente.nome}"
        campaign, created = Campaign.objects.get_or_create(
            cliente=cliente,
            name=campaign_name,
            defaults={
                "status": Campaign.Status.ACTIVE,
                "media_type": Campaign.MediaType.ONLINE,
                "start_date": timezone.now(),
                "end_date": timezone.now(),
            },
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f"Campanha criada: {campaign_name}"))
        else:
            self.stdout.write(f"Campanha existente: {campaign_name}")

        # Group rows by veiculo+tema
        imported = 0
        skipped = 0
        veiculos_summary = {}

        for row in rows:
            veiculo_raw = row.get("veiculo", "").strip().lower()
            tema = row.get("tema", "").strip()
            campanha = row.get("campanha", "").strip()

            if not veiculo_raw:
                skipped += 1
                continue

            media_channel = VEICULO_MAP.get(veiculo_raw, PlacementLine.MediaChannel.OTHER)

            # Parse numeric values
            def to_float(v):
                try:
                    return float(v) if v else 0.0
                except (ValueError, TypeError):
                    return 0.0

            def to_int(v):
                try:
                    return int(float(v)) if v else 0
                except (ValueError, TypeError):
                    return 0

            investimento = to_float(row.get("investimento", 0))
            impressoes = to_int(row.get("impressoes", 0))
            cliques = to_int(row.get("cliques", 0))
            engajamento = to_int(row.get("engajamento", 0))
            alcance = to_int(row.get("alcance", 0))

            # Build a unique external ref
            ext_ref = f"xlsx:{veiculo_raw}:{tema}"[:120]
            line_name = f"{tema}" if tema else campanha
            line_name = line_name[:100]

            if dry_run:
                self.stdout.write(
                    f"  [DRY] {veiculo_raw:20s} | {line_name:40s} | "
                    f"R$ {investimento:>12,.2f} | {impressoes:>10,} imp | {cliques:>8,} clk"
                )
            else:
                # Create PlacementLine
                placement_line, _ = PlacementLine.objects.update_or_create(
                    campaign=campaign,
                    external_ref=ext_ref,
                    defaults={
                        "media_type": PlacementLine.MediaType.ONLINE,
                        "media_channel": media_channel,
                        "market": cliente.nome,
                        "channel": line_name,
                        "property_text": campanha[:250] if campanha else "",
                    },
                )

                # Create PlacementDay (use today as date since Excel has no date column)
                today = date.today()
                PlacementDay.objects.update_or_create(
                    placement_line=placement_line,
                    date=today,
                    defaults={
                        "impressions": impressoes,
                        "clicks": cliques,
                        "cost": round(investimento, 2),
                    },
                )

            imported += 1
            veiculos_summary[veiculo_raw] = veiculos_summary.get(veiculo_raw, 0) + 1

        # Summary
        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"{'[DRY RUN] ' if dry_run else ''}Importadas: {imported} linhas, "
                f"Ignoradas: {skipped} (sem veiculo)"
            )
        )
        self.stdout.write("")
        self.stdout.write("Por veiculo:")
        for v, cnt in sorted(veiculos_summary.items(), key=lambda x: -x[1]):
            channel = VEICULO_MAP.get(v, "other")
            self.stdout.write(f"  {v:20s} -> {channel:20s} ({cnt} linhas)")
