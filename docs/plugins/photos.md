# Photos & Personal Media Plugins

Personal photo libraries are a good fit for Alcove's view-layer model: index the metadata, leave the originals where they are. None of these plugins upload images to an external service.

## CLIP Photo Search

**Library:** [`open-clip-torch`](https://github.com/mlfoundations/open_clip)

Embeds photos and text queries in a shared vector space using OpenCLIP. A query like "sunset over water" or "birthday cake with candles" returns semantically relevant photos without requiring tags or albums. Runs on your own hardware. No cloud account needed.

Multiple CLIP model variants are available. Larger models (ViT-L, ViT-H) give better retrieval quality at higher compute cost. The default configuration works on a modern laptop CPU, though a GPU speeds up initial indexing significantly.

## Face Clustering

**Library:** [`facenet-pytorch`](https://github.com/timesler/facenet-pytorch)

Groups photos by detected face identity using FaceNet embeddings. No biometric data leaves the machine. Useful for organizing large archives where album structure has broken down, or for finding all photos of a specific person across decades of files.

Clustering is approximate. Expect some errors at low confidence thresholds. The plugin returns cluster assignments as metadata; the user decides what to do with them.

## EXIF and GPS Metadata

**Library:** [`exifread`](https://github.com/ianare/exif-py)

Extracts structured metadata from image files: capture date, GPS coordinates, camera make and model, lens information, exposure settings. This metadata indexes alongside semantic embeddings, enabling compound queries: "photos taken in Iceland in winter with a wide-angle lens."

GPS coordinates are stored as-is. If you want human-readable location names, combine this plugin with a reverse geocoding step (not included by default).

## Scene Classification

**Library:** [Places365](http://places2.csail.mit.edu) via [`torch`](https://pytorch.org)

Tags photos with one of 365 location categories from the Places365 dataset: beach, forest, kitchen, art gallery, highway, etc. Useful as a coarse filter on large archives before running more expensive semantic search. The tags are stored as metadata and appear in filter facets.

## iCloud Photo Library (macOS)

**Library:** [`osxphotos`](https://github.com/RhetTbull/osxphotos)

Reads the local iCloud Photo Library on macOS directly, without export. Extracts Apple's own metadata: albums, smart albums, detected faces, location, keywords, favorites, and hidden status. Works on the SQLite database that Photos.app maintains locally.

This plugin only works on macOS where the Photos library is present. It reads; it does not write. Your library is not modified.
