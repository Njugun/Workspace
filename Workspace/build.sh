# Build script run by Render each time the site is deployed. Stops at the first error.
set -o errexit

pip install -r requirements.txt

# The stylesheet isn't stored in Git, so build it here.
mkdir -p assets
python manage.py tailwind build

python manage.py collectstatic --noinput
python manage.py migrate