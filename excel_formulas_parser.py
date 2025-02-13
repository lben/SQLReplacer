import openpyxl
from openpyxl.utils import column_index_from_string, get_column_letter
from functools import lru_cache
from typing import Dict, Set, List, Optional
import re

class ExcelFormulaDependencyParser:
    def __init__(self, file_path: str, header_row: int = 1, formula_row: int = 2):
        """
        Initialize the parser with configurable row numbers
        
        Args:
            file_path (str): Path to the Excel file
            header_row (int): Row number containing headers (1-based indexing)
            formula_row (int): Row number containing formulas (1-based indexing)
        """
        self.file_path = file_path
        self.header_row = header_row
        self.formula_row = formula_row
        self.wb = None
        self.headers = {}  # Sheet name -> {col_letter: header}
        self.formulas = {}  # Sheet name -> {col_letter: formula}
        
    @lru_cache(maxsize=1)
    def load_workbook(self):
        """Load workbook with caching to avoid repeated reads, only reading necessary rows"""
        if not self.wb:
            # Configure read_only for better performance
            self.wb = openpyxl.load_workbook(
                self.file_path,
                data_only=False,
                read_only=True,
                properties=True  # Load workbook properties for sheet names
            )
            self._cache_headers_and_formulas()
        return self.wb
    
    def _cache_headers_and_formulas(self):
        """Cache headers and formulas from specified rows"""
        wb = self.load_workbook()
        max_row = max(self.header_row, self.formula_row)
        
        for sheet_name in wb.sheetnames:
            self.headers[sheet_name] = {}
            self.formulas[sheet_name] = {}
            
            # Create a new worksheet reader for each sheet
            ws = wb[sheet_name]
            
            # Only iterate through rows up to formula_row
            for row_idx, row in enumerate(ws.iter_rows(min_row=1, max_row=max_row, values_only=False), start=1):
                for cell in row:
                    if cell.value:
                        col_letter = get_column_letter(cell.column)
                        
                        # Store headers
                        if row_idx == self.header_row:
                            self.headers[sheet_name][col_letter] = cell.value
                            
                        # Store formulas
                        elif row_idx == self.formula_row:
                            self.formulas[sheet_name][col_letter] = (
                                cell.value if isinstance(cell.value, str) and cell.value.startswith('=') 
                                else None
                            )
            
            # Close the worksheet to free memory
            ws.parent._archive.close()

    def _parse_column_references(self, formula: str) -> Set[tuple]:
        """Extract column references from a formula"""
        col_refs = set()
        
        # Handle VLOOKUP references
        vlookup_pattern = r'VLOOKUP\s*\((.*?),\s*(.*?!)?(.*?),'
        vlookup_matches = re.finditer(vlookup_pattern, formula, re.IGNORECASE)
        for match in vlookup_matches:
            sheet_ref = match.group(2)[:-1] if match.group(2) else None
            range_ref = match.group(3).strip('[]')
            if ':' in range_ref:
                start_col, end_col = range_ref.split(':')[0], range_ref.split(':')[1]
                start_col = ''.join(c for c in start_col if c.isalpha())
                end_col = ''.join(c for c in end_col if c.isalpha())
                col_refs.add((sheet_ref, start_col))
                col_refs.add((sheet_ref, end_col))
            else:
                col = ''.join(c for c in range_ref if c.isalpha())
                col_refs.add((sheet_ref, col))

        # Handle direct column references - adjust pattern to use formula_row
        direct_ref_pattern = f'([A-Za-z]+){self.formula_row}'
        for col in re.finditer(direct_ref_pattern, formula):
            col_refs.add((None, col.group(1)))
            
        return col_refs

    def build_dependency_tree(self, sheet_name: str, column: str) -> dict:
        """Build a dependency tree for a given column"""
        def _build_tree(sheet: str, col: str, visited: Set[tuple]) -> dict:
            node = {
                'name': f"{self.headers[sheet][col] if col in self.headers[sheet] else col}",
                'children': []
            }
            
            current = (sheet, col)
            if current in visited:
                return node
            visited.add(current)
            
            formula = self.formulas[sheet].get(col)
            if formula:
                dependencies = self._parse_column_references(formula)
                for dep_sheet, dep_col in dependencies:
                    dep_sheet = dep_sheet or sheet
                    if (dep_sheet, dep_col) not in visited:
                        child_tree = _build_tree(dep_sheet, dep_col, visited)
                        node['children'].append(child_tree)
            
            return node

        self.load_workbook()  # Ensure workbook is loaded
        return _build_tree(sheet_name, column, set())

    def print_tree(self, tree: dict, indent: str = "", is_last: bool = True):
        """Print the dependency tree in a Windows explorer-like format"""
        prefix = "└── " if is_last else "├── "
        print(f"{indent}{prefix}{tree['name']}")
        
        child_indent = indent + ("    " if is_last else "│   ")
        children = tree['children']
        
        for i, child in enumerate(children):
            is_last_child = i == len(children) - 1
            self.print_tree(child, child_indent, is_last_child)

    def __del__(self):
        """Cleanup method to ensure workbook is closed"""
        if self.wb:
            self.wb.close()

# Example usage:
if __name__ == "__main__":
    # Example with custom row numbers
    parser = ExcelFormulaDependencyParser(
        "your_excel_file.xlsx",
        header_row=3,    # Headers are in row 3
        formula_row=4    # Formulas are in row 4
    )
    tree = parser.build_dependency_tree("Sheet1", "B")  # Analyze column B in Sheet1
    parser.print_tree(tree)