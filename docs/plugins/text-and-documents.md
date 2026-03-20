# Text & Document Plugins

These plugins extend what Alcove can ingest. Each one handles a file format that the default text extractor does not cover. Install the ones you need; leave out the ones you don't.

## Office Formats

**Libraries:** [`python-pptx`](https://github.com/scanny/python-pptx), [`openpyxl`](https://openpyxl.readthedocs.io), [`odfpy`](https://github.com/eea/odfpy)

Extracts text and metadata from PowerPoint slides, Excel spreadsheets, and OpenDocument files. Slide text is extracted per-slide; spreadsheet text is extracted per-sheet. Useful for research archives, corporate document stores, and institutional knowledge bases where most content lives in Office formats.

## RTF

**Library:** [`striprtf`](https://github.com/joshy/striprtf)

Strips RTF markup and extracts plain text. RTF is a legacy format, but a lot of archives contain it. Legal filings, old word processing exports, and scanned-to-text workflows from the 1990s and 2000s often produce RTF. This plugin makes those files searchable.

## HTML and Web Archives

**Libraries:** [`trafilatura`](https://github.com/adbar/trafilatura), [`beautifulsoup4`](https://www.crummy.com/software/BeautifulSoup/)

Extracts main content from HTML files, discarding navigation, ads, and boilerplate. Handles downloaded web pages, WARC files, and browser exports. Trafilatura is the primary extractor; BeautifulSoup handles edge cases and structured extraction (tables, metadata tags).

## Markdown

**Library:** [`mistletoe`](https://github.com/miyuchina/mistletoe)

Parses Markdown and chunks by heading hierarchy. Works well for Obsidian vaults, Logseq graphs, wiki exports, and documentation repositories. Each heading section becomes a separate chunk with the heading path as metadata, so queries can return a specific section rather than an entire file.

## Recipe Data

**Libraries:** [`extruct`](https://github.com/scrapinghub/extruct), [`recipe-scrapers`](https://github.com/hhursev/recipe-scrapers)

Extracts structured ingredient and method data from HTML pages that use [Schema.org Recipe](https://schema.org/Recipe) markup. The result is structured metadata: ingredient list, yield, cook time, cuisine. Enables natural-language recipe search over a personal collection of saved pages.

## Inventory Scanning

**Stack:** [`pyzbar`](https://github.com/NaturalHistoryMuseum/pyzbar) + vision model

Reads barcodes from images (UPC, QR, EAN, etc.) and looks up product data. The result is a searchable inventory record: product name, manufacturer, category, and any metadata the barcode lookup returns. Useful for home inventory, library collections, or equipment tracking.

Requires a vision model for images where the barcode needs to be located before decoding.
