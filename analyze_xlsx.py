import pandas as pd

xlsx = pd.ExcelFile('demo2.xlsx')

with open('excel_analysis.txt', 'w', encoding='utf-8') as f:
    f.write('=== SHEETS ===\n')
    for name in xlsx.sheet_names:
        f.write(f'  - {name}\n')

    f.write('\n')
    for name in xlsx.sheet_names:
        df = pd.read_excel(xlsx, sheet_name=name, header=None)
        f.write(f'=== SHEET: {name} ===\n')
        f.write(f'Rows: {len(df)}, Cols: {len(df.columns)}\n')
        f.write('First 30 rows:\n')
        for idx, row in df.head(30).iterrows():
            row_vals = []
            for col_idx, v in enumerate(row):
                if pd.notna(v):
                    s = str(v)[:35]
                    row_vals.append(f'C{col_idx+1}:{s}')
            if row_vals:
                f.write(f'  R{idx+1}: {", ".join(row_vals)}\n')
        f.write('\n')

print('Analysis saved to excel_analysis.txt')
