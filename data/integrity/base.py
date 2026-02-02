"""
Base classes for data integrity checks.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from pathlib import Path
import json


@dataclass
class IntegrityCheckResult:
    """Result of a single integrity check."""
    
    check_name: str
    check_time: datetime
    status: str  # "ok", "warning", "error"
    summary: Dict[str, Any]
    details: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary for JSON serialization."""
        return {
            "check_name": self.check_name,
            "check_time": self.check_time.isoformat(),
            "status": self.status,
            "summary": self.summary,
            "details": self.details,
            "metadata": self.metadata,
        }


class IntegrityCheck(ABC):
    """Base class for data integrity checks."""
    
    def __init__(self, name: str, output_dir: Optional[Path] = None):
        """
        Initialize integrity check.
        
        Args:
            name: Name of the check
            output_dir: Directory to save results (defaults to reports/integrity)
        """
        self.name = name
        if output_dir is None:
            project_root = Path(__file__).resolve().parent.parent.parent
            output_dir = project_root / "reports" / "integrity"
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    @abstractmethod
    def run(self) -> IntegrityCheckResult:
        """Run the integrity check and return results."""
        pass
    
    def save_result(self, result: IntegrityCheckResult) -> tuple[Path, Path]:
        """
        Save check result to JSON and text files.
        
        Returns:
            Tuple of (json_path, txt_path)
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save JSON
        json_path = self.output_dir / f"{self.name}_{timestamp}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, indent=2, ensure_ascii=False)
        
        # Save text report
        txt_path = self.output_dir / f"{self.name}_{timestamp}.txt"
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write("=" * 80 + "\n")
            f.write(f"DATA INTEGRITY CHECK: {self.name}\n")
            f.write("=" * 80 + "\n\n")
            f.write(f"Check Time: {result.check_time.isoformat()}\n")
            f.write(f"Status: {result.status.upper()}\n")
            f.write("\n")
            f.write("SUMMARY\n")
            f.write("-" * 80 + "\n")
            for key, value in result.summary.items():
                f.write(f"{key}: {value}\n")
            f.write("\n")
            
            if result.details:
                f.write("DETAILS\n")
                f.write("-" * 80 + "\n")
                for detail in result.details:
                    f.write(f"{json.dumps(detail, indent=2, ensure_ascii=False)}\n")
                    f.write("\n")
        
        return json_path, txt_path
