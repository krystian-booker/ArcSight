import sys
from harvesters.core import Harvester

# --- IMPORTANT ---
# Change this to the full path of your GenTL Producer (.cti) file.
# Use forward slashes '/' even on Windows.
CTI_FILE_PATH = './Spinnaker_GenTL.cti' 

# Create a Harvester object
h = Harvester()

try:
    # Load the CTI file
    h.add_file(CTI_FILE_PATH)

    # Update the list of available devices
    h.update()

    # Check if any devices were found
    if not h.device_info_list:
        print("No GenICam devices found.")
        # Clean up and exit
        h.reset()
        sys.exit(1)

    # Print information about the found devices
    print("Found devices:", h.device_info_list)

    # Acquire an image from the first available device
    with h.create_image_acquirer(index=0) as ia:
        print("Starting image acquisition...")
        ia.start_image_acquisition()

        # Fetch a single buffer (which contains the image)
        with ia.fetch_buffer() as buffer:
            # The buffer object has a 'payload' which contains the image data.
            # For this test, we'll just confirm we got it.
            print(f"Successfully acquired an image!")
            print(f"  - Width: {buffer.payload.components[0].width}")
            print(f"  - Height: {buffer.payload.components[0].height}")
            print(f"  - Pixel Format: {buffer.payload.components[0].data_format}")

        print("Stopping image acquisition.")
        ia.stop_image_acquisition()

except Exception as e:
    print(f"An error occurred: {e}")

finally:
    # Clean up the harvester resources
    print("Resetting harvester.")
    h.reset()