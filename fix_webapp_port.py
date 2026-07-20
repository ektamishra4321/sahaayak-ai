"""Fix webapp.py: correct app.run indentation + ensure 'import os' exists.
Put inside sahaayak-ai folder, run:  python fix_webapp_port.py
"""
import os
import re

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "webapp.py")

NEW_RUN = '    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), debug=False)'

src = open(PATH, encoding="utf-8").read()

# 1. Replace the app.run line (any indentation, any current form) with correctly indented version
src, n = re.subn(r"^[ \t]*app\.run\(.*$", NEW_RUN, src, flags=re.M)
print(f"app.run line fixed ({n} replacement)")

# 2. Ensure 'import os' exists as a real import line
if not re.search(r"^import os\b", src, flags=re.M):
    src = src.replace("import logging", "import logging\nimport os", 1)
    print("added 'import os'")
else:
    print("'import os' already present")

open(PATH, "w", encoding="utf-8").write(src)

# 3. Syntax check
import ast
try:
    ast.parse(open(PATH, encoding="utf-8").read())
    print("Syntax OK. Now run:  python webapp.py  (Ctrl+C to stop after it starts)")
except SyntaxError as e:
    print(f"SYNTAX ERROR still present: line {e.lineno}: {e.msg}")
