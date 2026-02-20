def allowed_file(filename, allowed):

    return (
        "." in filename and
        filename.rsplit(".", 1)[1].lower() in allowed
    )


def allowed_photo_file(filename):

    return allowed_file(
        filename,
        {"jpg", "jpeg", "png", "gif"}
    )
