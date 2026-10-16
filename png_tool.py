from pathlib import Path
from PIL import Image, ImageOps, ImageFile, ImageDraw, ImageFont
import math
import re
import sys

# Guard against accidentally creating or loading enormous images.
MAX_PIXELS = 100_000_000
MAX_CELL_SIZE = 1024

RESAMPLING = {
    "1": ("Nearest Neighbor (pixel art)", Image.Resampling.NEAREST),
    "2": ("Lanczos (smooth artwork)", Image.Resampling.LANCZOS),
    "3": ("Bicubic (balanced)", Image.Resampling.BICUBIC),
    "4": ("Bilinear (softer)", Image.Resampling.BILINEAR),
}


def ask_choice(prompt, options, default=None):
    """Keep asking until the user selects a valid option."""
    while True:
        choice = input(prompt).strip()
        if choice in options:
            return choice
        if default is not None and choice == "":
            return default
        print("Invalid choice. Available options:", ", ".join(options.keys()))


def ask_positive_int(prompt, maximum=None, default=None):
    """Read and validate a positive integer."""
    while True:
        raw = input(prompt).strip()
        if raw == "" and default is not None:
            return default
        try:
            value = int(raw)
            if value <= 0:
                print("Value must be greater than zero.")
            elif maximum is not None and value > maximum:
                print(f"Value must not exceed {maximum:,}.")
            else:
                return value
        except ValueError:
            print("Please enter a valid integer.")


def natural_sort_key(value):
    """Sort names naturally: sprite2.png comes before sprite10.png."""
    return [int(part) if part.isdigit() else part.casefold()
            for part in re.split(r"(\d+)", str(value))]


def load_image(path):
    """Load the first frame of an image and normalize EXIF orientation."""
    with Image.open(path) as source:
        if getattr(source, "n_frames", 1) > 1:
            print("Note: this image has multiple frames; using the first frame:", path.name)
        source.seek(0)
        normalized = ImageOps.exif_transpose(source)
        normalized.load()
        return normalized.copy()


def choose_resize(img):
    """Choose a scale factor or exact target dimensions."""
    print("\nResize options:")
    print("1. Keep original dimensions")
    print("2. 2x upscale")
    print("3. 3x upscale")
    print("4. 4x upscale")
    print("5. Custom scale factor")
    print("6. Custom width and height")

    choice = ask_choice("Select: ", {
        "1": "original", "2": "2x", "3": "3x",
        "4": "4x", "5": "custom", "6": "dimensions"
    })
    width, height = img.size

    if choice == "1":
        return width, height, "1x"
    if choice in {"2", "3", "4"}:
        scale = int(choice)
        return width * scale, height * scale, f"{scale}x"
    if choice == "5":
        while True:
            try:
                scale = float(input("Scale factor (e.g. 1.5, 2, 0.5): ").strip())
                if math.isfinite(scale) and 0 < scale <= 100:
                    break
                print("Enter a factor greater than 0 and at most 100.")
            except ValueError:
                print("Enter a valid number.")
        return max(1, round(width * scale)), max(1, round(height * scale)), f"{scale:g}x"

    new_w = ask_positive_int("Target width: ", MAX_PIXELS)
    new_h = ask_positive_int("Target height: ", MAX_PIXELS)
    return new_w, new_h, f"{new_w}x{new_h}"


def choose_mode(img):
    """Convert to a selected PNG-supported color mode."""
    print("\nColor modes:")
    print("1. Grayscale (L, 8-bit; removes transparency)")
    print("2. Indexed palette (P, up to 256 colors)")
    print("3. RGB (24-bit; removes transparency)")
    print("4. RGBA (32-bit; preserves transparency)")
    print("5. Grayscale + alpha (LA)")
    print("6. Keep original mode when possible")

    choice = ask_choice("Select: ", {
        "1": "L", "2": "P", "3": "RGB",
        "4": "RGBA", "5": "LA", "6": "KEEP"
    })

    has_alpha = "A" in img.getbands() or "transparency" in img.info
    if choice == "1":
        return img.convert("L")
    if choice == "2":
        if has_alpha:
            return img.convert("RGBA").quantize(
                colors=256, method=Image.Quantize.FASTOCTREE
            )
        return img.convert("RGB").quantize(
            colors=256, method=Image.Quantize.MEDIANCUT
        )
    if choice == "3":
        return img.convert("RGB")
    if choice == "4":
        return img.convert("RGBA")
    if choice == "5":
        return img.convert("LA")
    if img.mode in {"RGB", "RGBA", "L", "LA", "P"}:
        return img.copy()
    return img.convert("RGBA" if has_alpha else "RGB")


def process_single_image():
    """Process one image and save it as PNG without overwriting existing files."""
    raw_path = input("\nEnter image path (or drag a file here): ").strip().strip('"').strip("'")
    if not raw_path:
        print("Error: No path entered.")
        return

    input_path = Path(raw_path).expanduser()
    if not input_path.is_file():
        print(f"Error: File not found:\n{input_path}")
        return

    try:
        with Image.open(input_path) as probe:
            if probe.width * probe.height > MAX_PIXELS:
                print(f"Error: Image exceeds the {MAX_PIXELS:,}-pixel safety limit.")
                return

        img = load_image(input_path)
        print(f"\nLoaded: {input_path.name}")
        print(f"Dimensions: {img.width} x {img.height}")
        print(f"Mode: {img.mode}")
        print("Transparency:", "Yes" if ("A" in img.getbands() or "transparency" in img.info) else "No")

        new_w, new_h, size_label = choose_resize(img)
        if new_w * new_h > MAX_PIXELS:
            print("Error: Target dimensions exceed the pixel limit.")
            return

        print("\nResampling methods:")
        for key, (name, _) in RESAMPLING.items():
            print(f"{key}. {name}")
        method_choice = ask_choice("Select resampling method [1]: ", RESAMPLING, default="1")
        method_name, resampling = RESAMPLING[method_choice]

        if img.size != (new_w, new_h):
            img = img.resize((new_w, new_h), resampling)
        print(f"Resized: {img.width} x {img.height} ({method_name})")

        img = choose_mode(img)
        print(f"Output mode: {img.mode}")

        custom_dir = input("\nOutput directory (Enter = same folder): ").strip().strip('"').strip("'")
        output_dir = Path(custom_dir).expanduser() if custom_dir else input_path.parent
        output_dir.mkdir(parents=True, exist_ok=True)

        print("\nPNG compression:")
        print("1. Fast save")
        print("2. Balanced")
        print("3. Maximum lossless compression")
        compression_choice = ask_choice(
            "Select [2]: ", {"1": "fast", "2": "balanced", "3": "maximum"}, default="2"
        )
        compression = {"1": 1, "2": 6, "3": 9}[compression_choice]

        base_name = f"{input_path.stem}_processed_{size_label}"
        output_path = output_dir / f"{base_name}.png"
        counter = 1
        while output_path.exists():
            output_path = output_dir / f"{base_name}_{counter}.png"
            counter += 1

        img.save(output_path, format="PNG", optimize=(compression_choice == "3"),
                 compress_level=compression)
        with Image.open(output_path) as check:
            check.verify()

        print("\n" + "=" * 42)
        print("SUCCESS")
        print(f"File: {output_path}")
        print(f"Dimensions: {img.width} x {img.height}")
        print(f"Mode: {img.mode}")
        print(f"Size: {output_path.stat().st_size:,} bytes")
        print("=" * 42)

    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        print(f"\nImage processing error: {exc}")
    except KeyboardInterrupt:
        print("\nOperation cancelled.")
    except Exception as exc:
        print(f"\nUnexpected error: {type(exc).__name__}: {exc}")


def load_font(size):
    """Try common fonts, falling back to Pillow's built-in font."""
    candidates = [
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/Library/Fonts/Arial.ttf",
        "DejaVuSans.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except (OSError, ValueError):
            continue
    return ImageFont.load_default()


def truncate_label(text, draw, font, max_width):
    """Shorten a long filename/path so it fits in a cell label."""
    try:
        measured = text
        draw.textbbox((0, 0), measured, font=font)
    except (UnicodeEncodeError, ValueError):
        measured = text.encode("ascii", "replace").decode("ascii")

    suffix = "..."
    while measured and draw.textbbox((0, 0), measured, font=font)[2] > max_width:
        measured = measured[:-1]
    if measured != text and len(measured) > len(suffix):
        measured = measured[:-len(suffix)].rstrip() + suffix
    return measured


def make_rows_for_width(image_specs, target_width, gap, label_height, padding):
    """Pack images into natural-order rows without resizing any source image."""
    rows = []
    row = []
    row_width = 0
    row_height = 0

    for spec in image_specs:
        width, height = spec["size"]
        tile_height = height + label_height
        proposed_width = width if not row else row_width + gap + width

        if row and proposed_width > target_width:
            rows.append({"items": row, "width": row_width, "height": row_height})
            row = []
            row_width = 0
            row_height = 0
            proposed_width = width

        if row:
            row_width += gap + width
        else:
            row_width = width

        row.append(spec)
        row_height = max(row_height, tile_height)

    if row:
        rows.append({"items": row, "width": row_width, "height": row_height})

    canvas_width = max((row_info["width"] for row_info in rows), default=0) + 2 * padding
    canvas_height = (
        sum(row_info["height"] for row_info in rows)
        + max(0, len(rows) - 1) * gap
        + 2 * padding
    )
    return rows, (canvas_width, canvas_height)


def choose_compact_layout(image_specs, gap, padding, label_height):
    """Choose a compact layout whose canvas is as close to square as practical."""
    max_width = max(spec["size"][0] for spec in image_specs)
    total_width = sum(spec["size"][0] for spec in image_specs) + gap * max(0, len(image_specs) - 1)
    occupied_area = sum(
        width * (height + label_height)
        for spec in image_specs
        for width, height in [spec["size"]]
    )

    # Try a range of target widths. Image dimensions are never changed; only row
    # breaks change. Candidate widths are capped to avoid wasteful layouts.
    ideal = max(1, int(math.sqrt(occupied_area)))
    lower = max_width
    upper = min(total_width, max(max_width, int(ideal * 2.25)))
    if upper < lower:
        upper = lower

    candidate_widths = {lower, upper}
    samples = 180
    if upper > lower:
        for index in range(samples + 1):
            candidate_widths.add(
                round(lower + (upper - lower) * index / samples)
            )

    # Include likely near-square widths explicitly, reducing sensitivity to the
    # sampling interval for common sprite sizes.
    for multiplier in (0.60, 0.70, 0.80, 0.90, 1.00, 1.10, 1.25, 1.40, 1.60, 1.85, 2.10, 2.25):
        candidate_widths.add(max(lower, min(upper, int(ideal * multiplier))))

    best = None
    for target_width in sorted(candidate_widths):
        rows, canvas_size = make_rows_for_width(
            image_specs, target_width, gap, label_height, padding
        )
        canvas_width, canvas_height = canvas_size
        pixel_count = canvas_width * canvas_height
        if canvas_width <= 0 or canvas_height <= 0 or pixel_count > MAX_PIXELS:
            continue

        aspect_penalty = abs(math.log(canvas_width / canvas_height))
        occupied_ratio = min(1.0, occupied_area / pixel_count)
        empty_ratio = 1.0 - occupied_ratio
        # Prefer near-square sheets but avoid layouts that achieve this by
        # creating an excessive amount of unused canvas.
        score = aspect_penalty + 0.22 * empty_ratio
        if best is None or score < best[0]:
            best = (score, rows, canvas_size, target_width)

    return best


def create_contact_sheet():
    """Combine PNGs at native dimensions into one compact, near-square sheet."""
    raw_folder = input("\nEnter the folder containing PNG files: ").strip().strip('"').strip("'")
    if not raw_folder:
        print("Error: No folder entered.")
        return

    folder = Path(raw_folder).expanduser()
    if not folder.is_dir():
        print(f"Error: Folder not found:\n{folder}")
        return

    recursive_choice = ask_choice(
        "Include PNGs in subfolders? (y/N): ",
        {"y": "yes", "Y": "yes", "n": "no", "N": "no", "": "no"},
        default="n",
    )
    recursive = recursive_choice.lower() == "y"
    candidates = folder.rglob("*") if recursive else folder.iterdir()

    png_paths = []
    for path in candidates:
        if not path.is_file() or path.suffix.lower() != ".png":
            continue
        # Prevent the output from being added as an input on later runs.
        if re.match(r"^(png_)?contact_sheet(?:_\d+)?$", path.stem, re.IGNORECASE):
            continue
        png_paths.append(path)

    png_paths.sort(key=lambda p: natural_sort_key(p.relative_to(folder).as_posix()))
    if not png_paths:
        print("No PNG files found (excluding previously generated contact sheets).")
        return

    print(f"Found {len(png_paths)} PNG file(s). Reading their original dimensions...")
    image_specs = []
    skipped = []
    total_source_pixels = 0

    # Validate each file and record dimensions. No thumbnails or resizing are used.
    for path in png_paths:
        try:
            with Image.open(path) as source:
                source.seek(0)
                width, height = source.size
                if width <= 0 or height <= 0:
                    skipped.append((path, "invalid image dimensions"))
                    continue
                if width * height > MAX_PIXELS:
                    skipped.append((path, f"image exceeds {MAX_PIXELS:,}-pixel safety limit"))
                    continue
                source.load()  # Detect truncated/corrupt images before layout.
            image_specs.append({"path": path, "size": (width, height)})
            total_source_pixels += width * height
        except (OSError, ValueError, Image.DecompressionBombError) as exc:
            skipped.append((path, str(exc)))
        except Exception as exc:
            skipped.append((path, f"{type(exc).__name__}: {exc}"))

    if not image_specs:
        print("No readable PNG files could be used.")
        for path, reason in skipped[:20]:
            print(f"- {path.name}: {reason}")
        return

    if total_source_pixels > MAX_PIXELS:
        print(
            f"Error: The source images alone contain {total_source_pixels:,} pixels, "
            f"exceeding the {MAX_PIXELS:,}-pixel output safety limit. "
            "Split them into smaller folders/sheets."
        )
        return

    print("\nLayout: each PNG keeps its exact original width and height.")
    print("The output dimensions are calculated from source sizes, gaps, and optional labels.")
    try:
        raw_gap = input("Gap between images in pixels [8] (0-256): ").strip()
        gap = 8 if raw_gap == "" else int(raw_gap)
        if not 0 <= gap <= 256:
            print("Gap must be between 0 and 256 pixels.")
            return
    except ValueError:
        print("Please enter a valid whole number for the gap.")
        return

    labels_choice = ask_choice(
        "Add filename labels below each image? (Y/n): ",
        {"y": "yes", "Y": "yes", "n": "no", "N": "no", "": "yes"},
        default="y",
    )
    show_labels = labels_choice.lower() != "n"
    label_height = 26 if show_labels else 0

    print("\nBackground:")
    print("1. Transparent (preserves source alpha; recommended)")
    print("2. Light gray")
    print("3. White")
    print("4. Dark gray")
    bg_choice = ask_choice(
        "Select background [1]: ",
        {"1": "transparent", "2": "light", "3": "white", "4": "dark"},
        default="1",
    )
    transparent_sheet = bg_choice == "1"
    backgrounds = {
        "2": (242, 242, 242),
        "3": (255, 255, 255),
        "4": (48, 48, 48),
    }
    bg_color = backgrounds.get(bg_choice)

    # Use an outer margin equal to the inter-image gap; with gap=0 there is no margin.
    padding = gap
    layout = choose_compact_layout(image_specs, gap, padding, label_height)
    if layout is None:
        print(
            "Error: Even the most compact candidate layout exceeds the "
            f"{MAX_PIXELS:,}-pixel safety limit. Reduce labels/gaps or split the folder."
        )
        return

    _, rows, (sheet_width, sheet_height), target_width = layout
    if transparent_sheet:
        sheet = Image.new("RGBA", (sheet_width, sheet_height), (0, 0, 0, 0))
        label_band = (238, 238, 238, 235)
        label_ink = (20, 20, 20, 255)
        border = (150, 150, 150, 255)
    else:
        sheet = Image.new("RGB", (sheet_width, sheet_height), bg_color)
        if bg_choice == "4":
            label_band, label_ink, border = (65, 65, 65), (255, 255, 255), (125, 125, 125)
        else:
            label_band, label_ink, border = (225, 225, 225), (25, 25, 25), (175, 175, 175)

    draw = ImageDraw.Draw(sheet)
    font = load_font(14)
    placed = 0
    current_y = padding

    for row_info in rows:
        current_x = padding
        for spec in row_info["items"]:
            path = spec["path"]
            width, height = spec["size"]
            try:
                with Image.open(path) as source:
                    source.seek(0)
                    # No resize, thumbnail, crop, or EXIF rotation: native pixel dimensions stay intact.
                    asset = source.convert("RGBA")
                    asset.load()

                if asset.size != (width, height):
                    skipped.append((path, "dimensions changed while processing; omitted"))
                    current_x += width + gap
                    continue

                if transparent_sheet:
                    # Direct paste preserves the asset's alpha channel on the transparent canvas.
                    sheet.paste(asset, (current_x, current_y))
                else:
                    # Composite transparency onto the selected opaque background.
                    sheet.paste(asset, (current_x, current_y), asset.getchannel("A"))

                if show_labels:
                    band_y = current_y + height
                    draw.rectangle(
                        (current_x, band_y, current_x + width - 1, band_y + label_height - 1),
                        fill=label_band,
                    )
                    label = path.relative_to(folder).as_posix() if recursive else path.name
                    label = truncate_label(label, draw, font, max(1, width - 8))
                    if width > 12 and label:
                        draw.text((current_x + 4, band_y + 5), label, fill=label_ink, font=font)

                placed += 1
            except (OSError, ValueError, Image.DecompressionBombError) as exc:
                skipped.append((path, str(exc)))
            except Exception as exc:
                skipped.append((path, f"{type(exc).__name__}: {exc}"))
            current_x += width + gap
        current_y += row_info["height"] + gap

    if placed == 0:
        print("No images could be placed in the contact sheet.")
        return

    output_path = folder / "png_contact_sheet.png"
    counter = 1
    while output_path.exists():
        output_path = folder / f"png_contact_sheet_{counter}.png"
        counter += 1

    try:
        sheet.save(output_path, format="PNG", optimize=True)
        with Image.open(output_path) as check:
            check.verify()
    except (OSError, ValueError) as exc:
        print(f"Could not save the contact sheet: {exc}")
        return

    print("\n" + "=" * 52)
    print("NATIVE-SIZE CONTACT SHEET CREATED")
    print(f"Output: {output_path}")
    print(f"Readable source PNGs: {len(image_specs)}")
    print(f"Images placed: {placed}")
    print(f"Skipped/unreadable: {len(skipped)}")
    print(f"Canvas resolution: {sheet.width} x {sheet.height} pixels")
    print(f"Layout target width: {target_width} pixels (used only to choose row breaks)")
    print(f"Source pixels: {total_source_pixels:,} total; none were resized")
    print(f"Labels: {'yes' if show_labels else 'no'}; gap: {gap}px")
    print(f"File size: {output_path.stat().st_size:,} bytes")
    if skipped:
        print("\nSkipped files:")
        for path, reason in skipped[:20]:
            try:
                display_path = path.relative_to(folder)
            except ValueError:
                display_path = path
            print(f"- {display_path}: {reason}")
        if len(skipped) > 20:
            print(f"... and {len(skipped) - 20} more.")
    print("=" * 52)

def main():
    print("=" * 46)
    print("        SMART PNG IMAGE PROCESSOR")
    print("=" * 46)
    print("1. Process / upscale one image")
    print("2. Combine PNGs at native sizes into one compact artwork")
    choice = ask_choice("\nSelect mode: ", {"1": "single", "2": "sheet"})
    if choice == "1":
        process_single_image()
    else:
        create_contact_sheet()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nOperation cancelled.")
        sys.exit(130)
