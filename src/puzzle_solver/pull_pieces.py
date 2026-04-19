# Pull out puzzle piece contours from an image and save individual masks.

# python .\pull_pieces.py --image ..\sample_images\simple_1_rotated.png --outdir ..\output
import argparse, json, os
import logging
import cv2 as cv
import numpy as np

logger = logging.getLogger(__name__)

def ensure_dir(p):
    os.makedirs(p, exist_ok=True)

def preprocess(img):
    # robust contrast + denoise to help thresholding
    lab = cv.cvtColor(img, cv.COLOR_BGR2LAB)
    l,a,b = cv.split(lab)
    clahe = cv.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
    l = clahe.apply(l)
    lab = cv.merge([l,a,b])
    img_eq = cv.cvtColor(lab, cv.COLOR_LAB2BGR)
    blur = cv.GaussianBlur(img_eq, (5,5), 0)
    gray = cv.cvtColor(blur, cv.COLOR_BGR2GRAY)
    return gray

def _validate_min_area(min_area):
    if isinstance(min_area, str):
        min_area = min_area.strip()

    try:
        resolved_min_area = int(min_area)
    except (TypeError, ValueError) as exc:
        raise ValueError("min_area must be an integer") from exc

    if resolved_min_area < 0:
        raise ValueError("min_area must be non-negative")

    return resolved_min_area

def _validate_threshold(threshold_value):
    if threshold_value is None:
        return None

    if isinstance(threshold_value, str):
        normalized = threshold_value.strip().lower()
        if normalized in {"", "none", "otsu"}:
            return None
        try:
            threshold_value = int(normalized)
        except ValueError as exc:
            raise ValueError(
                "threshold_value must be an integer, 'none', or 'otsu'"
            ) from exc

    if not isinstance(threshold_value, int):
        raise ValueError("threshold_value must be an integer, 'none', or 'otsu'")

    if not 0 <= threshold_value <= 255:
        raise ValueError("threshold_value must be between 0 and 255")
    return threshold_value

def _border_white_fraction(mask):
    border = np.concatenate(
        (mask[0, :], mask[-1, :], mask[:, 0], mask[:, -1])
    )
    return float(np.count_nonzero(border)) / float(border.size)

def _select_foreground_polarity(mask):
    inverted = cv.bitwise_not(mask)
    # Puzzle pieces should usually not dominate the image border.
    if _border_white_fraction(inverted) < _border_white_fraction(mask):
        return inverted
    return mask

def segment_foreground(gray, threshold_value=None):
    # Configurable threshold with Otsu fallback, followed by morphology to isolate pieces
    threshold_value = _validate_threshold(threshold_value)
    if threshold_value is None:
        _, bw = cv.threshold(gray, 0, 255, cv.THRESH_BINARY + cv.THRESH_OTSU)
    else:
        _, bw = cv.threshold(gray, threshold_value, 255, cv.THRESH_BINARY)
    bw = _select_foreground_polarity(bw)
    kernel = cv.getStructuringElement(cv.MORPH_ELLIPSE, (5,5))
    bw = cv.morphologyEx(bw, cv.MORPH_OPEN, kernel, iterations=2)
    bw = cv.morphologyEx(bw, cv.MORPH_CLOSE, kernel, iterations=2)
    # fill small holes
    cnts, _ = cv.findContours(bw, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE)
    mask = np.zeros_like(bw)
    cv.drawContours(mask, cnts, -1, 255, thickness=cv.FILLED)
    return mask

def find_pieces(mask, min_area=2000):
    # label connected components via contours
    min_area = _validate_min_area(min_area)
    contours, _ = cv.findContours(mask, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_NONE)
    contours = [c for c in contours if cv.contourArea(c) >= min_area]
    contours.sort(key=lambda c: cv.boundingRect(c)[:2])
    return contours

def save_contours_only(img, contours, outdir):
    summary = []
    paths = []
    for idx, c in enumerate(contours, start=1):
        area = cv.contourArea(c)
        perim = cv.arcLength(c, True)

        # save a binary mask of each contour
        piece_mask = np.zeros(img.shape[:2], dtype=np.uint8)
        cv.drawContours(piece_mask, [c], -1, 255, thickness=cv.FILLED)
        path = os.path.join(outdir, f"piece_{idx}.png")
        paths.append(path)
        cv.imwrite(path, piece_mask)

        summary.append({
            "piece_id": idx,
            "area_px": float(area),
            "perimeter_px": float(perim)
        })

    with open(os.path.join(outdir, "edges.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    return summary, paths

def pull_pieces(image, outdir, min_area=60000, threshold_value=None) -> list[str]:
    ensure_dir(outdir)

    gray = preprocess(image)

    if threshold_value is None:
        candidate_thresholds = [80, 100,120, 140, 160, 180, 200, 220]

        best_contours = None

        for tv in candidate_thresholds:
            fg = segment_foreground(gray, threshold_value=tv)
            contours = find_pieces(fg, min_area=min_area)

            if len(contours) in (4, 6):
                best_contours = contours  # keep updating => return highes threshold that yields 4 or 6 contours, to avoid overfitting to noise
                logger.debug("Tried threshold %s: found %d contours with size %s", tv, len(contours), [cv.contourArea(c) for c in contours])


        # fallback: if no valid threshold found, just use last attempt
        if best_contours is None:
            fg = segment_foreground(gray, threshold_value=candidate_thresholds[-1])
            best_contours = find_pieces(fg, min_area=min_area)

    else:
        fg = segment_foreground(gray, threshold_value=threshold_value)
        best_contours = find_pieces(fg, min_area=min_area)

    summary, paths = save_contours_only(image, best_contours, outdir)
    return paths


def main():
    ap = argparse.ArgumentParser(description="Detect puzzle piece edges and interlocks")
    ap.add_argument("--image", required=True, help="path to input image")
    ap.add_argument("--outdir", default="output", help="folder to save results")
    ap.add_argument("--min_area", type=int, default=60000, help="min contour area to keep")
    ap.add_argument(
        "--threshold",
        default=None,
        help="fixed grayscale threshold for foreground segmentation; defaults to Otsu",
    )
    args = ap.parse_args()

    ensure_dir(args.outdir)

    img = cv.imread(args.image)
    if img is None:
        raise SystemExit(f"Could not read image: {args.image}")
    
    paths = pull_pieces(
        img,
        args.outdir,
        min_area=args.min_area,
        threshold_value=args.threshold,
    )
    logger.info("Saved %d piece masks to %s", len(paths), args.outdir)

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    main()
