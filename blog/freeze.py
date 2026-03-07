import os
from flask_frozen import Freezer
from app import app, fetch_bitable_records

# Force relative URLs so it works in GitHub Pages sub-directories
app.config['FREEZER_RELATIVE_URLS'] = True

freezer = Freezer(app)

@freezer.register_generator
def detail():
    # Tell Freezer how to generate all dynamic article pages
    records = fetch_bitable_records()
    for record in records:
        yield {'record_id': record['id']}

if __name__ == '__main__':
    freezer.freeze()
