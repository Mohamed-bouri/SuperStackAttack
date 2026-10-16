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


def create_contact_sheet():
    """Arrange PNG files into one square, labeled contact sheet."""
    raw_folder = input("\nEnter the folder containing PNG files: ").strip().strip('"').strip("'")
    if not raw_folder:
        print("Error: No folder entered.")
        return

    folder = Path(raw_folder).expanduser()
    if not folder.is_dir():
        print(f"Error: Folder not found:\n{folder}")
        return

    recursive_choice = ask_choice(
        "Include PNGs in subfolders? (y/N): ", {"y": "yes", "Y": "yes", "n": "no", "N": "no", "": "no"}, default="n"
    )
    recursive = recursive_choice.lower() == "y"

    if recursive:
        candidates = folder.rglob("*")
    else:
        candidates = folder.iterdir()

    png_paths = []
    for path in candidates:
        if not path.is_file() or path.suffix.lower() != ".png":
            continue
        # Exclude this tool's own contact-sheet outputs on later runs.
        if re.match(r"^(png_)?contact_sheet(?:_\d+)?$", path.stem, re.IGNORECASE):
            continue
        png_paths.append(path)

    png_paths.sort(key=lambda p: natural_sort_key(p.relative_to(folder).as_posix()))
    if not png_paths:
        print("No PNG files found in the selected folder (after excluding previous contact sheets).")
        return

    print(f"Found {len(png_paths)} PNG file(s).")
    cell_size = ask_positive_int("Square cell size in pixels [256]: ", MAX_CELL_SIZE, default=256)
    if cell_size < 96:
        print("Cell size below 96 can make labels and thumbnails hard to inspect; continuing anyway.")

    labels_choice = ask_choice(
        "Add filename labels? (Y/n): ", {"y": "yes", "Y": "yes", "n": "no", "N": "no", "": "yes"}, default="y"
    )
    show_labels = labels_choice.lower() != "n"

    print("\nBackground:")
    print("1. Light gray (recommended)")
    print("2. White")
    print("3. Dark gray")
    print("4. Transparent")
    bg_choice = ask_choice("Select background [1]: ", {"1": "light", "2": "white", "3": "dark", "4": "transparent"}, default="1")
    backgrounds = {
        "1": (242, 242, 242),
        "2": (255, 255, 255),
        "3": (48, 48, 48),
    }
    bg_color = backgrounds.get(bg_choice)
    transparent_sheet = bg_choice == "4"

    count = len(png_paths)
    grid_side = math.ceil(math.sqrt(count))
    gap = max(8, round(cell_size * 0.04))
    padding = gap
    sheet_side = padding * 2 + grid_side * cell_size + (grid_side - 1) * gap
    if sheet_side * sheet_side > MAX_PIXELS:
        print(
            f"Error: The contact sheet would be {sheet_side} x {sheet_side} "
            f"({sheet_side * sheet_side:,} pixels), exceeding the safety limit. "
            "Use a smaller cell size or fewer files."
        )
        return

    if transparent_sheet:
        sheet = Image.new("RGBA", (sheet_side, sheet_side), (0, 0, 0, 0))
        label_band = (245, 245, 245, 235)
        label_ink = (20, 20, 20, 255)
        border = (150, 150, 150, 255)
    else:
        sheet = Image.new("RGB", (sheet_side, sheet_side), bg_color)
        if bg_choice == "3":
            label_band, label_ink, border = (65, 65, 65), (255, 255, 255), (125, 125, 125)
        else:
            label_band, label_ink, border = (225, 225, 225), (25, 25, 25), (175, 175, 175)

    draw = ImageDraw.Draw(sheet)
    font_size = max(10, min(24, cell_size // 16))
    font = load_font(font_size)
    label_height = max(24, font_size + 10) if show_labels else 0
    image_margin = max(6, round(cell_size * 0.04))
    image_box = (
        max(1, cell_size - image_margin * 2),
        max(1, cell_size - image_margin * 2 - label_height),
    )

    skipped = []
    placed = 0
    for index, path in enumerate(png_paths, start=1):
        try:
            with Image.open(path) as source:
                source.seek(0)
                asset = ImageOps.exif_transpose(source).convert("RGBA")
                asset.load()
            if asset.width * asset.height > MAX_PIXELS:
                skipped.append((path, "image exceeds pixel safety limit"))
                continue

            thumbnail = ImageOps.contain(asset, image_box, method=Image.Resampling.LANCZOS)
            col = (index - 1) % grid_side
            row = (index - 1) // grid_side
            x = padding + col * (cell_size + gap)
            y = padding + row * (cell_size + gap)

            # Center thumbnail without stretching or discarding its alpha channel.
            tx = x + (cell_size - thumbnail.width) // 2
            ty = y + (image_box[1] - thumbnail.height) // 2 + image_margin
            if transparent_sheet:
                sheet.alpha_composite(thumbnail, (tx, ty))
            else:
                tile_bg = Image.new("RGBA", thumbnail.size, (*bg_color, 255))
                tile_bg.alpha_composite(thumbnail)
                sheet.paste(tile_bg.convert("RGB"), (tx, ty))

            # Cell outline makes the sheet visually structured.
            draw.rectangle((x, y, x + cell_size - 1, y + cell_size - 1), outline=border, width=1)

            if show_labels:
                band_y = y + cell_size - label_height
                draw.rectangle((x + 1, band_y, x + cell_size - 2, y + cell_size - 2), fill=label_band)
                try:
                    label = path.relative_to(folder).as_posix() if recursive else path.name
                    label = f"{index:03d}  {label}"
                    label = truncate_label(label, draw, font, cell_size - image_margin * 2)
                except Exception:
                    label = f"{index:03d}  [filename]"
                draw.text((x + image_margin, band_y + 3), label, fill=label_ink, font=font)

            placed += 1
        except (OSError, ValueError, Image.DecompressionBombError) as exc:
            skipped.append((path, str(exc)))
        except Exception as exc:
            skipped.append((path, f"{type(exc).__name__}: {exc}"))

    if placed == 0:
        print("No readable PNG files could be placed in the contact sheet.")
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

    print("\n" + "=" * 48)
    print("CONTACT SHEET CREATED")
    print(f"Output: {output_path}")
    print(f"PNG files found: {count}")
    print(f"Images placed: {placed}")
    print(f"Skipped: {len(skipped)}")
    print(f"Canvas: {sheet.width} x {sheet.height} pixels (square)")
    print(f"Cell size: {cell_size} x {cell_size} pixels")
    print(f"File size: {output_path.stat().st_size:,} bytes")
    if skipped:
        print("\nSkipped files:")
        for path, reason in skipped[:20]:
            print(f"- {path.relative_to(folder)}: {reason}")
        if len(skipped) > 20:
            print(f"... and {len(skipped) - 20} more.")
    print("=" * 48)


def main():
    print("=" * 46)
    print("        SMART PNG IMAGE PROCESSOR")
    print("=" * 46)
    print("1. Process / upscale one image")
    print("2. Combine a folder of PNGs into one square artwork")
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
