import logging
from pathlib import Path
from typing import Optional, List, Tuple, Callable
from PIL import Image, ImageStat
from src.models.translation_item import PageTranslation, BubbleBlock
from src.services.onnx_bubble_detector import OnnxBubbleDetector

logger = logging.getLogger(__name__)


class MangaOcrDetector:
    """
    100% Local Manga Speech Bubble Detection and OCR Engine.
    - Detection: ComicTextDetector via OnnxBubbleDetector (CPU ONNX).
    - OCR: MangaOcr via manga-ocr-torchless (CPU ONNX).
    - ZERO images are ever transmitted externally or sent to any LLM.
    """
    def __init__(
        self,
        api_key: str = "",
        base_url: str = "",
        model: str = "",
        ocr_engine=None,
        min_variance: float = 6.0,
        ocr_model_path: str = "",
        force_cpu: bool = False,
        detector: Optional[OnnxBubbleDetector] = None,
    ):
        self.api_key = api_key.strip()
        self.base_url = base_url.strip()
        self.model = model.strip()
        self._engine = ocr_engine
        self.min_variance = float(min_variance)
        self.ocr_model_path = ocr_model_path.strip() if ocr_model_path else ""
        self.force_cpu = bool(force_cpu)
        self._onnx_detector = detector or OnnxBubbleDetector(force_cpu=self.force_cpu)
        # Engine is loaded lazily on demand when OCR is first needed in background thread

    def _init_engine(self):
        if self._engine is not None:
            return
        try:
            from manga_ocr import MangaOcr  # type: ignore
            kwargs = {"force_cpu": self.force_cpu}
            if self.ocr_model_path:
                kwargs["pretrained_model_name_or_path"] = self.ocr_model_path
            self._engine = MangaOcr(**kwargs)
            logger.info("Loaded local manga-ocr engine successfully.")
        except Exception as e:
            logger.warning(f"Could not initialize local manga-ocr engine: {e}")
            self._engine = None

    def is_bubble_detector_available(self) -> bool:
        """Returns True if local speech bubble detection model is available."""
        return bool(self._onnx_detector and self._onnx_detector.is_available())

    def ensure_bubble_detector(
        self,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None
    ) -> bool:
        """
        Ensures local speech bubble detection model is available on disk.
        If missing, downloads it automatically via AiAssetsManager.
        """
        if self.is_bubble_detector_available():
            return True
        from src.services.ai_assets_manager import AiAssetsManager
        model_path = AiAssetsManager().download_comic_model(
            progress_callback=progress_callback,
            cancel_check=cancel_check
        )
        if self._onnx_detector:
            self._onnx_detector.model_path = model_path
            self._onnx_detector._available = None
            self._onnx_detector._session = None
        return True

    def recognize_crop(self, crop_img: Image.Image) -> str:
        """Run local OCR on a cropped image region, returning recognized text."""
        self._init_engine()
        if self._engine is not None:
            return self._engine(crop_img).strip()
        return ""

    def segment_bubble(
        self,
        full_img: Image.Image,
        bbox: Tuple[int, int, int, int],
        other_bboxes: Optional[List[Tuple[int, int, int, int]]] = None
    ) -> Tuple[Tuple[int, int, int, int], Tuple[int, int], str]:
        """Calculates expanded speech balloon bounding box, true centroid, and shape classification."""
        return self._segment_bubble(full_img, bbox, other_bboxes=other_bboxes)

    def detect_and_ocr_manual_region(
        self,
        full_img: Image.Image,
        bbox: Tuple[int, int, int, int]
    ) -> Tuple[str, Tuple[int, int, int, int], Tuple[int, int], str]:
        """
        Public method to OCR and segment a manual bounding box on a full page image.
        Returns: (text_ja, expanded_bbox, centroid, shape_type)
        """
        bx, by, bw, bh = bbox
        crop_x1 = max(0, bx - 6)
        crop_y1 = max(0, by - 6)
        crop_x2 = min(full_img.width, bx + bw + 6)
        crop_y2 = min(full_img.height, by + bh + 6)
        crop = full_img.crop((crop_x1, crop_y1, crop_x2, crop_y2))

        text_ja = ""
        try:
            text_ja = self.recognize_crop(crop)
        except Exception as e:
            logger.warning(f"OCR error on manual region: {e}")

        exp_bbox, cent, shape_type = self._segment_bubble(full_img, bbox)
        return text_ja, exp_bbox, cent, shape_type

    def _segment_bubble(
        self,
        full_img: Image.Image,
        bbox: Tuple[int, int, int, int],
        other_bboxes: Optional[List[Tuple[int, int, int, int]]] = None
    ) -> Tuple[Tuple[int, int, int, int], Tuple[int, int], str]:
        """
        Calculates expanded speech balloon bounding box, true centroid, and shape classification (oval vs box).
        Masks out neighboring speech bubbles to prevent floodfill expansion from colliding across boundaries.
        """
        bx, by, bw, bh = bbox
        default_res = ((bx, by, bw, bh), (bx + bw // 2, by + bh // 2), "oval")
        try:
            import cv2
            import numpy as np

            orig_w, orig_h = full_img.size
            pad_x = int(bw * 1.3 + 25)
            pad_y = int(bh * 0.5 + 25)
            x1 = max(0, bx - pad_x)
            y1 = max(0, by - pad_y)
            x2 = min(orig_w, bx + bw + pad_x)
            y2 = min(orig_h, by + bh + pad_y)

            crop_pil = full_img.crop((x1, y1, x2, y2)).convert("L")
            crop = np.array(crop_pil)
            h_c, w_c = crop.shape

            tb_x1 = max(0, bx - x1)
            tb_y1 = max(0, by - y1)
            tb_x2 = min(w_c, bx + bw - x1)
            tb_y2 = min(h_c, by + bh - y1)

            obs = (crop <= 140).astype(np.uint8)
            obs_closed = cv2.morphologyEx(
                obs, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (13, 13))
            )
            # Inset obstacle clearing by 8% to preserve bubble and narration box boundary walls
            ix = max(4, int(bw * 0.08))
            iy = max(4, int(bh * 0.08))
            obs = (crop <= 140).astype(np.uint8)
            obs_closed = cv2.morphologyEx(
                obs, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))
            )
            obs_closed[tb_y1 + iy:tb_y2 - iy, tb_x1 + ix:tb_x2 - ix] = 0

            # If neighboring dialogue boxes exist in the crop window, mark them as solid obstacles
            # so floodfill never leaks into or swallows adjacent dialogue balloons
            if other_bboxes:
                for obx, oby, obw, obh in other_bboxes:
                    if (obx, oby, obw, obh) == (bx, by, bw, bh):
                        continue
                    ox1 = max(0, obx - x1)
                    oy1 = max(0, oby - y1)
                    ox2 = min(w_c, obx + obw - x1)
                    oy2 = min(h_c, oby + obh - y1)
                    if ox2 > ox1 and oy2 > oy1:
                        obs_closed[oy1:oy2, ox1:ox2] = 1

            trav = (obs_closed == 0).astype(np.uint8) * 255
            cx = (tb_x1 + tb_x2) // 2
            cy = (tb_y1 + tb_y2) // 2

            mask = np.zeros((h_c + 2, w_c + 2), np.uint8)
            cv2.floodFill(trav, mask, (cx, cy), 128)
            filled = (trav == 128).astype(np.uint8)

            # Check polarity: detect if text is white on dark background (e.g. title/narration over screentone)
            tb_crop = crop[tb_y1:tb_y2, tb_x1:tb_x2]
            is_inverted = np.mean(tb_crop <= 80) > 0.40 and np.mean(tb_crop >= 200) < 0.35
            if is_inverted:
                # Inverted text over art: keep tight padded rect without drawing a huge white bubble
                pad_rect = (
                    max(0, bx - 8),
                    max(0, by - 8),
                    min(orig_w - bx + 8, bw + 16),
                    min(orig_h - by + 8, bh + 16)
                )
                return pad_rect, (bx + bw // 2, by + bh // 2), "inverted"

            cnts, _ = cv2.findContours(filled, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not cnts:
                return default_res

            best_cnt = max(cnts, key=cv2.contourArea)
            rx, ry, rw, rh = cv2.boundingRect(best_cnt)
            gx, gy = x1 + rx, y1 + ry

            area = cv2.contourArea(best_cnt)
            hull = cv2.convexHull(best_cnt)
            hull_area = cv2.contourArea(hull)
            solidity = area / hull_area if hull_area > 0 else 0
            peri = cv2.arcLength(best_cnt, True)
            circ = 4 * np.pi * area / (peri * peri) if peri > 0 else 0
            rect_fill = area / (rw * rh) if rw * rh > 0 else 0

            # Check if region is a clean, solid rectangular box
            is_solid_box = (rect_fill >= 0.88 and solidity >= 0.90)

            # Reject leaks: gutter leaks, extreme blowouts, or geometric breakdown
            has_leaked = (
                (gx <= 2 and bx > 40) or
                (gy <= 2 and by > 40) or
                (gx + rw >= orig_w - 2 and bx + bw < orig_w - 40) or
                (rw > bw * 3.5) or
                (rh > bh * 2.5) or
                (not is_solid_box and (
                    solidity < 0.80 or
                    circ < 0.28 or
                    rw > bw * 1.65 or
                    rh > bh * 1.65 or
                    bx - gx > 50 or
                    (gx + rw) - (bx + bw) > 50
                ))
            )
            if has_leaked:
                pad_rect = (
                    max(0, bx - 8),
                    max(0, by - 8),
                    min(orig_w - bx + 8, bw + 16),
                    min(orig_h - by + 8, bh + 16)
                )
                return pad_rect, (bx + bw // 2, by + bh // 2), "box"

            M = cv2.moments(best_cnt)
            if M["m00"] > 0:
                mcx = int(M["m10"] / M["m00"])
                mcy = int(M["m01"] / M["m00"])
            else:
                mcx, mcy = rx + rw // 2, ry + rh // 2
            centroid = (x1 + mcx, y1 + mcy)

            approx = cv2.approxPolyDP(best_cnt, 0.03 * peri, True)
            if rect_fill >= 0.88 or len(approx) == 4 or circ < 0.60:
                shape_type = "box"
            else:
                shape_type = "oval"
            return (gx, gy, rw, rh), centroid, shape_type
        except Exception as e:
            logger.debug(f"Bubble expansion failed for bbox {bbox}: {e}")
        return default_res

    def _split_multi_lobe_bubble(
        self,
        full_img: Image.Image,
        bbox: Tuple[int, int, int, int]
    ) -> List[Tuple[int, int, int, int]]:
        """
        Detects if a bounding box covers a multi-lobe / figure-8 bubble with two separate text clusters
        and splits it into distinct dialogue bboxes. Never splits rectangular narration boxes.
        """
        bx, by, bw, bh = bbox
        if bw < 50 or bh < 120:
            return [bbox]

        # Never split rectangular narration boxes
        _, _, shape_type = self._segment_bubble(full_img, bbox)
        if shape_type == "box":
            return [bbox]

        try:
            import cv2
            import numpy as np

            crop = np.array(full_img.crop((bx, by, bx + bw, by + bh)).convert("L"))
            ret, thresh = cv2.threshold(crop, 140, 255, cv2.THRESH_BINARY_INV)
            num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(thresh)

            text_comps = [
                i for i in range(1, num_labels)
                if 15 < stats[i, cv2.CC_STAT_AREA] < 800
                and stats[i, cv2.CC_STAT_WIDTH] < bw * 0.75
                and stats[i, cv2.CC_STAT_HEIGHT] < 70
            ]
            if len(text_comps) < 4:
                return [bbox]

            centers_y = [centroids[i][1] for i in text_comps]
            mid_y = bh * 0.5
            top_group = [i for i in text_comps if centroids[i][1] < mid_y]
            bot_group = [i for i in text_comps if centroids[i][1] >= mid_y]

            if len(top_group) >= 2 and len(bot_group) >= 2:
                top_xs = [centroids[i][0] for i in top_group]
                bot_xs = [centroids[i][0] for i in bot_group]

                # If the two text clusters have substantial horizontal separation (e.g. diagonal lobes of figure 8)
                if abs(float(np.mean(top_xs)) - float(np.mean(bot_xs))) > bw * 0.30:
                    top_x1 = min(stats[i, cv2.CC_STAT_LEFT] for i in top_group)
                    top_y1 = min(stats[i, cv2.CC_STAT_TOP] for i in top_group)
                    top_x2 = max(stats[i, cv2.CC_STAT_LEFT] + stats[i, cv2.CC_STAT_WIDTH] for i in top_group)
                    top_y2 = max(stats[i, cv2.CC_STAT_TOP] + stats[i, cv2.CC_STAT_HEIGHT] for i in top_group)

                    bot_x1 = min(stats[i, cv2.CC_STAT_LEFT] for i in bot_group)
                    bot_y1 = min(stats[i, cv2.CC_STAT_TOP] for i in bot_group)
                    bot_x2 = max(stats[i, cv2.CC_STAT_LEFT] + stats[i, cv2.CC_STAT_WIDTH] for i in bot_group)
                    bot_y2 = max(stats[i, cv2.CC_STAT_TOP] + stats[i, cv2.CC_STAT_HEIGHT] for i in bot_group)

                    sub1 = (int(bx + top_x1), int(by + top_y1), int(top_x2 - top_x1), int(top_y2 - top_y1))
                    sub2 = (int(bx + bot_x1), int(by + bot_y1), int(bot_x2 - bot_x1), int(bot_y2 - bot_y1))
                    return [sub1, sub2]
        except Exception as e:
            logger.debug(f"Error checking multi-lobe split for {bbox}: {e}")

        return [bbox]

    def detect_page(self, image_path: Path, page_index: int = 1, log_callback=None) -> PageTranslation:
        """
        Detect speech bubbles and extract text 100% locally.
        Optimized single-decode workflow:
        - Decodes image from disk only once into memory.
        - Pre-scales oversized scans (>1600px) for rapid ONNX detection.
        - Maps detected bounding boxes back to native resolution for precise cropping and UI overlay.
        """
        image_path = Path(image_path)
        full_img = None
        detect_img = None
        try:
            full_img = Image.open(image_path)
            orig_width, orig_height = full_img.size
            if full_img.mode != "RGB":
                full_img = full_img.convert("RGB")
        except Exception as e:
            err = f"Failed to open image {image_path}: {e}"
            logger.error(err)
            if log_callback:
                log_callback(err)
            return PageTranslation(page_filename=image_path.name, page_width=0, page_height=0, bubbles=[])

        try:
            # 1. Pre-scale image for fast ONNX text detection if oversized
            MAX_DETECT_DIM = 1600
            max_dim = max(orig_width, orig_height)
            if max_dim > MAX_DETECT_DIM:
                scale = MAX_DETECT_DIM / float(max_dim)
                scaled_w = max(1, int(orig_width * scale))
                scaled_h = max(1, int(orig_height * scale))
                detect_img = full_img.resize((scaled_w, scaled_h), Image.Resampling.BILINEAR)
            else:
                scale = 1.0
                detect_img = full_img

            detected_bboxes: List[Tuple[int, int, int, int]] = []
            if self._onnx_detector.is_available():
                try:
                    raw_bboxes = self._onnx_detector.detect_bubbles(detect_img)
                    if scale != 1.0:
                        inv_scale = 1.0 / scale
                        for bx, by, bw, bh in raw_bboxes:
                            orig_x = max(0, min(int(bx * inv_scale), orig_width - 1))
                            orig_y = max(0, min(int(by * inv_scale), orig_height - 1))
                            orig_w = max(1, min(int(bw * inv_scale), orig_width - orig_x))
                            orig_h = max(1, min(int(bh * inv_scale), orig_height - orig_y))
                            detected_bboxes.append((orig_x, orig_y, orig_w, orig_h))
                    else:
                        detected_bboxes = raw_bboxes

                    if detected_bboxes:
                        msg = f"Detected {len(detected_bboxes)} speech bubbles locally via ONNX on {image_path.name}"
                        logger.info(msg)
                        if log_callback:
                            log_callback(msg)
                except Exception as e:
                    err_msg = f"Local ONNX detection error on {image_path.name}: {e}"
                    logger.warning(err_msg)
                    if log_callback:
                        log_callback(err_msg)
            else:
                err_msg = (
                    f"Speech bubble detection model (comic-text-detector.onnx) is missing. "
                    f"Cannot detect dialogue bubbles on {image_path.name}."
                )
                logger.warning(err_msg)
                if log_callback:
                    log_callback(err_msg)

            if not detected_bboxes:
                msg = f"No speech bubbles detected on {image_path.name}"
                logger.info(msg)
                if log_callback:
                    log_callback(msg)
                return PageTranslation(
                    page_filename=image_path.name,
                    page_width=orig_width,
                    page_height=orig_height,
                    bubbles=[]
                )

            # Split multi-lobe / figure-8 bubbles before OCR
            split_bboxes: List[Tuple[int, int, int, int]] = []
            for bbox in detected_bboxes:
                split_bboxes.extend(self._split_multi_lobe_bubble(full_img, bbox))
            split_bboxes.sort(key=lambda b: (b[1] // 160, -b[0]))
            detected_bboxes = split_bboxes

            # 2. Extract text locally from each bubble crop using in-memory full_img
            if self._engine is None:
                self._init_engine()

            bubbles: List[BubbleBlock] = []
            for bx, by, bw, bh in detected_bboxes:
                # Safe crop with 6px padding to prevent boundary glyph strokes from being clipped
                crop_x1 = max(0, bx - 6)
                crop_y1 = max(0, by - 6)
                crop_x2 = min(orig_width, bx + bw + 6)
                crop_y2 = min(orig_height, by + bh + 6)
                crop = full_img.crop((crop_x1, crop_y1, crop_x2, crop_y2))

                # Skip low-variance/blank crops (e.g. solid white/blank boxes, uniform screentone with no text)
                if self.min_variance > 0:
                    stat = ImageStat.Stat(crop.convert("L"))
                    if stat.stddev[0] < self.min_variance:
                        logger.debug(
                            "Skipping blank/low-variance bubble crop at (%d, %d, %d, %d) (stddev=%.2f < %.2f)",
                            bx, by, bw, bh, stat.stddev[0], self.min_variance
                        )
                        continue

                b_id = f"p{page_index}_b{len(bubbles) + 1}"
                raw_text = ""
                if self._engine is not None:
                    try:
                        raw_text = self._engine(crop).strip()
                    except Exception as e:
                        logger.warning(f"Error OCR-ing bubble {b_id}: {e}")

                exp_bbox, cent, shape_type = self._segment_bubble(
                    full_img, (bx, by, bw, bh), other_bboxes=detected_bboxes
                )

                bubbles.append(
                    BubbleBlock(
                        id=b_id,
                        bbox=(bx, by, bw, bh),
                        text_ja=raw_text,
                        text_en="",
                        expanded_bbox=exp_bbox,
                        centroid=cent,
                        shape=shape_type
                    )
                )

            # Post-segmentation boundary resolution:
            # If two sibling bubbles overlap vertically or horizontally, clamp their touching boundary to avoid occluding each other
            for i in range(len(bubbles)):
                b1 = bubbles[i]
                if not b1.expanded_bbox:
                    continue
                x1, y1, w1, h1 = b1.expanded_bbox
                for j in range(i + 1, len(bubbles)):
                    b2 = bubbles[j]
                    if not b2.expanded_bbox:
                        continue
                    x2, y2, w2, h2 = b2.expanded_bbox
                    # Check horizontal alignment
                    inter_x1 = max(x1, x2)
                    inter_x2 = min(x1 + w1, x2 + w2)
                    inter_w = max(0, inter_x2 - inter_x1)
                    if inter_w > min(w1, w2) * 0.35:
                        # Stacking collision: b1 above b2
                        if y1 < y2 and (y1 + h1) > y2:
                            overlap = (y1 + h1) - y2
                            if 0 < overlap < min(h1, h2) * 0.70:
                                split_y = y2 + overlap // 2
                                new_h1 = max(b1.bbox[3], split_y - y1)
                                new_y2 = min(b2.bbox[1], split_y)
                                new_h2 = max(b2.bbox[3], (y2 + h2) - new_y2)
                                b1.expanded_bbox = (x1, y1, w1, new_h1)
                                b2.expanded_bbox = (x2, new_y2, w2, new_h2)
                        # Stacking collision: b2 above b1
                        elif y2 < y1 and (y2 + h2) > y1:
                            overlap = (y2 + h2) - y1
                            if 0 < overlap < min(h1, h2) * 0.70:
                                split_y = y1 + overlap // 2
                                new_h2 = max(b2.bbox[3], split_y - y2)
                                new_y1 = min(b1.bbox[1], split_y)
                                new_h1 = max(b1.bbox[3], (y1 + h1) - new_y1)
                                b2.expanded_bbox = (x2, y2, w2, new_h2)
                                b1.expanded_bbox = (x1, new_y1, w1, new_h1)

            msg = f"Extracted {len(bubbles)} dialogue bubbles locally on {image_path.name}"
            logger.info(msg)
            if log_callback:
                log_callback(msg)

            return PageTranslation(
                page_filename=image_path.name,
                page_width=orig_width,
                page_height=orig_height,
                bubbles=bubbles
            )
        finally:
            if full_img is not None:
                try:
                    full_img.close()
                except Exception:
                    pass
            if detect_img is not None and detect_img is not full_img:
                try:
                    detect_img.close()
                except Exception:
                    pass
