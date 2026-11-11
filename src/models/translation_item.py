from dataclasses import dataclass, field, asdict
from typing import List, Tuple, Any, Dict, Optional

@dataclass
class BubbleBlock:
    id: str
    bbox: Tuple[int, int, int, int]  # (x, y, w, h)
    text_ja: str
    text_en: str = ""
    target_lang: str = ""
    expanded_bbox: Optional[Tuple[int, int, int, int]] = None
    centroid: Optional[Tuple[int, int]] = None
    shape: str = "oval"
    is_manual: bool = False

    def to_dict(self) -> Dict[str, Any]:
        res = {
            "id": self.id,
            "bbox": list(self.bbox),
            "text_ja": self.text_ja,
            "text_en": self.text_en,
            "shape": self.shape,
        }
        if self.target_lang:
            res["target_lang"] = self.target_lang
        if self.is_manual:
            res["is_manual"] = True
        if self.expanded_bbox is not None:
            res["expanded_bbox"] = list(self.expanded_bbox)
        if self.centroid is not None:
            res["centroid"] = list(self.centroid)
        return res

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BubbleBlock":
        bbox_data = data.get("bbox", [0, 0, 0, 0])
        exp_data = data.get("expanded_bbox")
        exp_bbox = (int(exp_data[0]), int(exp_data[1]), int(exp_data[2]), int(exp_data[3])) if exp_data else None
        cent_data = data.get("centroid")
        centroid = (int(cent_data[0]), int(cent_data[1])) if cent_data else None
        return cls(
            id=str(data.get("id", "")),
            bbox=(int(bbox_data[0]), int(bbox_data[1]), int(bbox_data[2]), int(bbox_data[3])),
            text_ja=str(data.get("text_ja", "")),
            text_en=str(data.get("text_en", "")),
            target_lang=str(data.get("target_lang", "")),
            expanded_bbox=exp_bbox,
            centroid=centroid,
            shape=str(data.get("shape", "oval")),
            is_manual=bool(data.get("is_manual", False)),
        )

@dataclass
class PageTranslation:
    page_filename: str
    page_width: int
    page_height: int
    bubbles: List[BubbleBlock] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "page_filename": self.page_filename,
            "page_width": self.page_width,
            "page_height": self.page_height,
            "bubbles": [b.to_dict() for b in self.bubbles],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PageTranslation":
        bubbles = [BubbleBlock.from_dict(b) for b in data.get("bubbles", [])]
        return cls(
            page_filename=str(data.get("page_filename", "")),
            page_width=int(data.get("page_width", 0)),
            page_height=int(data.get("page_height", 0)),
            bubbles=bubbles,
        )
