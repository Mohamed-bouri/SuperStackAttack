
from pathlib import Path
from PIL import Image, ImageOps, ImageFile
import sys

# Safety limit: avoid accidentally allocating enormous images.
MAX_PIXELS = 100_000_000

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

        print("Invalid choice. Available options:",
              ", ".join(options.keys()))


def ask_positive_int(prompt, maximum=None):
    """Read and validate a positive integer."""
    while True:
        try:
            value = int(input(prompt).strip())

            if value <= 0:
                print("Value must be greater than zero.")
            elif maximum is not None and value > maximum:
                print(f"Value must not exceed {maximum:,}.")
            else:
                return value

        except ValueError:
            print("Please enter a valid integer.")


def load_image(path):
    """Load an image safely and normalize its orientation."""
    with Image.open(path) as source:
        if getattr(source, "n_frames", 1) > 1:
            print("Note: this is an animated/multiframe image.")
            print("Only the first frame will be processed.")

        source.seek(0)
        img = ImageOps.exif_transpose(source)
        img.load()
        return img.copy()


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
                scale = float(input("Scale factor (e.g. 1.5, 2, 0.5): "))
                if 0 < scale <= 100:
                    break
                print("Enter a factor greater than 0 and at most 100.")
            except ValueError:
                print("Enter a valid number.")

        new_w = max(1, round(width * scale))
        new_h = max(1, round(height * scale))
        return new_w, new_h, f"{scale:g}x"

    new_w = ask_positive_int("Target width: ", MAX_PIXELS)
    new_h = ask_positive_int("Target height: ", MAX_PIXELS)

    return new_w, new_h, f"{new_w}x{new_h}"


def choose_mode(img):
    """Convert to the selected PNG color mode."""
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

    if choice == "1":
        return img.convert("L")

    if choice == "2":
        # Quantizing RGBA with FASTOCTREE supports transparency.
        if "A" in img.getbands() or "transparency" in img.info:
            rgba = img.convert("RGBA")
            return rgba.quantize(
                colors=256,
                method=Image.Quantize.FASTOCTREE
            )

        return img.convert("RGB").quantize(
            colors=256,
            method=Image.Quantize.MEDIANCUT
        )

    if choice == "3":
        return img.convert("RGB")

    if choice == "4":
        return img.convert("RGBA")

    if choice == "5":
        return img.convert("LA")

    # PNG supports RGB, RGBA, L, LA, and P modes.
    if img.mode in {"RGB", "RGBA", "L", "LA", "P"}:
        return img.copy()

    return img.convert("RGBA" if (
        "A" in img.getbands() or "transparency" in img.info
    ) else "RGB")


def process_png_tool():
    print("=" * 42)
    print("       SMART PNG IMAGE PROCESSOR")
    print("=" * 42)

    raw_path = input(
        "\nEnter image path (or drag a file here): "
    ).strip().strip('"').strip("'")

    if not raw_path:
        print("Error: No path entered.")
        return

    input_path = Path(raw_path).expanduser()

    if not input_path.is_file():
        print(f"Error: File not found:\n{input_path}")
        return

    try:
        # Pillow's decompression-bomb protection remains enabled.
        with Image.open(input_path) as probe:
            width, height = probe.size

            if width * height > MAX_PIXELS:
                print(
                    f"Error: Image contains {width * height:,} pixels. "
                    f"Limit: {MAX_PIXELS:,}."
                )
                return

        img = load_image(input_path)

        print(f"\nLoaded: {input_path.name}")
        print(f"Dimensions: {img.width} x {img.height}")
        print(f"Mode: {img.mode}")
        print(f"Transparency: {'Yes' if (
            'A' in img.getbands() or 'transparency' in img.info
        ) else 'No'}")

        # 1. Resize
        new_w, new_h, size_label = choose_resize(img)

        if new_w * new_h > MAX_PIXELS:
            print("Error: Target dimensions exceed the pixel limit.")
            return

        print("\nResampling methods:")
        for key, (name, _) in RESAMPLING.items():
            print(f"{key}. {name}")

        method_choice = ask_choice(
            "Select resampling method [1]: ",
            RESAMPLING,
            default="1"
        )
        method_name, resampling = RESAMPLING[method_choice]

        if img.size != (new_w, new_h):
            img = img.resize((new_w, new_h), resampling)

        print(f"Resized: {img.width} x {img.height}")
        print(f"Resampling: {method_name}")

        # 2. Color conversion
        img = choose_mode(img)
        print(f"Output mode: {img.mode}")

        # 3. Output directory
        custom_dir = input(
            "\nOutput directory (Enter = same folder): "
        ).strip().strip('"').strip("'")

        output_dir = (
            Path(custom_dir).expanduser()
            if custom_dir else input_path.parent
        )

        output_dir.mkdir(parents=True, exist_ok=True)

        # 4. PNG compression
        print("\nPNG compression:")
        print("1. Fast save")
        print("2. Balanced")
        print("3. Maximum lossless compression")

        compression_choice = ask_choice(
            "Select [2]: ",
            {"1": "fast", "2": "balanced", "3": "maximum"},
            default="2"
        )

        compression = {
            "1": 1,
            "2": 6,
            "3": 9
        }[compression_choice]

        # 5. Generate a unique output filename.
        base_name = f"{input_path.stem}_processed_{size_label}"
        output_path = output_dir / f"{base_name}.png"
        counter = 1

        while output_path.exists():
            output_path = output_dir / (
                f"{base_name}_{counter}.png"
            )
            counter += 1

        img.save(
            output_path,
            format="PNG",
            optimize=(compression_choice == "3"),
            compress_level=compression
        )

        # Verify that the output can be reopened.
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


if __name__ == "__main__":
    try:
        process_png_tool()
    except KeyboardInterrupt:
        print("\nOperation cancelled.")
        sys.exit(130)
