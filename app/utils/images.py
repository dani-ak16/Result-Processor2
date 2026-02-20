def compress_image(img_path, output_path, max_width=300, quality=70):
    img = Image.open(img_path)

    # --- FIX ORIENTATION ---
    try:
        for orientation in ExifTags.TAGS.keys():
            if ExifTags.TAGS[orientation] == 'Orientation':
                break

        exif = img._getexif()
        if exif is not None:
            orientation_value = exif.get(orientation)
            if orientation_value == 3:
                img = img.rotate(180, expand=True)
            elif orientation_value == 6:
                img = img.rotate(270, expand=True)
            elif orientation_value == 8:
                img = img.rotate(90, expand=True)
    except Exception:
        # If EXIF is missing or unreadable, skip orientation correction
        pass

    # --- RESIZE AND COMPRESS ---
    img.thumbnail((max_width, max_width), Image.LANCZOS)
    rgb_img = img.convert('RGB')
    rgb_img.save(output_path, format="JPEG", optimize=True, quality=quality)

    return output_path
