# Redaction Plan Schema

The plan is JSON and is intended to be reviewed before destructive redaction is applied.

```json
{
  "schema_version": 1,
  "source": {"name": "scan.pdf", "type": "pdf"},
  "settings": {"dpi": 200, "ocr_language": "eng"},
  "detections": [
    {
      "id": "d0001",
      "page": 1,
      "entity_type": "US_SSN",
      "source": "ocr",
      "bbox": [72.0, 140.0, 155.0, 154.0],
      "coordinate_space": "pdf_points",
      "ocr_confidence": 93.1,
      "detector_confidence": 1.0,
      "preview": "***-**-6789",
      "sha256": "...",
      "action": "redact"
    }
  ],
  "warnings": []
}
```

For images, `bbox` is `[left, top, right, bottom]` in source-image pixels and `coordinate_space` is `image_pixels`.

## Manual boxes

A reviewer may append a detection with:

- `entity_type`: `MANUAL`
- `source`: `manual`
- a correct bounding box and coordinate space
- `action`: `redact`

No sensitive plaintext is required to apply a manual box.
