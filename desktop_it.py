"""Launch the independent ORBIX Technologies (IT) Windows edition."""
import os

# Set this before desktop imports server so the IT edition receives its own
# program title and its own D:\\ORBIX Technologies IT\\orbix.db database.
os.environ['ORBIX_APP_VARIANT'] = 'it'

from desktop import main


if __name__ == '__main__':
    main()
