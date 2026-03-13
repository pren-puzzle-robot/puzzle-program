import cv2
import numpy as np
import glob

# Checkerboard size (inner corners)
CHECKERBOARD = (9,6)

criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)

objp = np.zeros((CHECKERBOARD[0]*CHECKERBOARD[1],3), np.float32)
objp[:,:2] = np.mgrid[0:CHECKERBOARD[0],0:CHECKERBOARD[1]].T.reshape(-1,2)

objpoints = []
imgpoints = []

images = glob.glob("images/*.JPG")

for fname in images:

    img = cv2.imread(fname)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    ret, corners = cv2.findChessboardCorners(gray, CHECKERBOARD, None)

    if ret:

        objpoints.append(objp)

        corners2 = cv2.cornerSubPix(
            gray,
            corners,
            (11,11),
            (-1,-1),
            criteria
        )

        imgpoints.append(corners2)

        cv2.drawChessboardCorners(img, CHECKERBOARD, corners2, ret)
        cv2.imshow("corners", img)
        cv2.waitKey(100)

cv2.destroyAllWindows()

ret, camera_matrix, dist_coeffs, rvecs, tvecs = cv2.calibrateCamera(
    objpoints,
    imgpoints,
    gray.shape[::-1],
    None,
    None
)

print("\nCamera matrix:\n")
print(camera_matrix)

print("\nDistortion coefficients:\n")
print(dist_coeffs)

np.savez(
    "gopro_calibration.npz",
    camera_matrix=camera_matrix,
    dist_coeffs=dist_coeffs
)

mean_error = 0

for i in range(len(objpoints)):
    imgpoints2, _ = cv2.projectPoints(
        objpoints[i],
        rvecs[i],
        tvecs[i],
        camera_matrix,
        dist_coeffs
    )

    error = cv2.norm(imgpoints[i], imgpoints2, cv2.NORM_L2) / len(imgpoints2)
    mean_error += error

print("Reprojection error:", mean_error / len(objpoints))