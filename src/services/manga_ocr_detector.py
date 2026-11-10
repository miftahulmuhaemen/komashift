import logging
from pathlib import Path
from typing import Optional, List, Tuple
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
        min_variance: float = 6.0
    ):
        self.api_key = api_key.strip()
        self.base_url = base_url.strip()
        self.model = model.strip()
        self._engine = ocr_engine
        self.min_variance = float(min_variance)
        self._onnx_detector = OnnxBubbleDetector()
        # Engine is loaded lazily on demand when OCR is first needed in background thread

    def _init_engine(self):
        if self._engine is not None:
            return
        try:
            from manga_ocr import MangaOcr  # type: ignore
            self._engine = MangaOcr()
            logger.info("Loaded local manga-ocr engine successfully.")
        except Exception as e:
            logger.warning(f"Could not initialize local manga-ocr engine: {e}")
            self._engine = None

    def _segment_bubble(
        self,
        full_img: Image.Image,
        bbox: Tuple[int, int, int, int]
    ) -> Tuple[Tuple[int, int, int, int], Tuple[int, int], str]:
        """
        Calculates expanded speech balloon bounding box, true centroid, and shape classification (oval vs box).
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

                exp_bbox, cent, shape_type = self._segment_bubble(full_img, (bx, by, bw, bh))

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
