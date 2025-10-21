from harvesters.core import Harvester
import cv2
import numpy as np

# Create a Harvester object
h = Harvester()

# Add the CTI file for your camera
h.add_file('/Applications/Spinnaker/lib/spinnaker-gentl/Spinnaker_GenTL.cti')

# Update the list of available devices
h.update()

# Check if any devices were found
if not h.device_info_list:
    print("No cameras found.")
    h.reset() # Clean up
    exit()

print("Cameras found:", h.device_info_list)

# --- Video Display Setup ---
# Create an OpenCV window
cv2.namedWindow("Video", cv2.WINDOW_NORMAL)

# Create an ImageAcquirer object for the first camera
# The 'with' statement ensures resources are released automatically
with h.create(0) as ia:
    # Configure the camera for continuous acquisition if needed
    # This is often the default, but can be set explicitly
    try:
        ia.remote_device.node_map.AcquisitionMode.value = 'Continuous'
    except Exception as e:
        print(f"Could not set AcquisitionMode to Continuous: {e}")

    # Start image acquisition
    ia.start()
    print("Started video stream. Press 'q' to exit.")

    # Loop to continuously fetch and display images
    while True:
        # Use a 'with' statement to fetch a buffer.
        # This automatically requeues the buffer when the block is exited.
        with ia.fetch() as buffer:
            # The payload contains the image data
            component = buffer.payload.components[0]

            # Reshape the 1D numpy array to a 2D image
            img = component.data.reshape(component.height, component.width)

            # --- Display the image with OpenCV ---
            cv2.imshow("Video", img)

        # Wait for a key press for 1 ms.
        # If 'q' is pressed, break the loop.
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

# Stop the image acquisition
ia.stop()

# Clean up OpenCV windows
cv2.destroyAllWindows()

# The harvester object is reset automatically when the initial 'with' block is exited
print("Script finished.")