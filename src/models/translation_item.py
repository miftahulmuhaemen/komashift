from dataclasses import dataclass, field, asdict
from typing import List, Tuple, Any, Dict

@dataclass
class BubbleBlock:
    id: str
    bbox: Tuple[int, int, int, int]  # (x, y, w, h)
    text_ja: str
    text_en: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "bbox": list(self.bbox),
            "text_ja": self.text_ja,
            "text_en": self.text_en,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BubbleBlock":
        bbox_data = data.get("bbox", [0, 0, 0, 0])
        return cls(
            id=str(data.get("id", "")),
            bbox=(int(bbox_data[0]), int(bbox_data[1]), int(bbox_data[2]), int(bbox_data[3])),
            text_ja=str(data.get("text_ja", "")),
            text_en=str(data.get("text_en", "")),
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
