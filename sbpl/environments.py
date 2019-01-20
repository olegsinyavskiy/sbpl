from __future__ import print_function
from __future__ import absolute_import
from __future__ import division


import sbpl._sbpl_module
import tempfile
import os
import shutil
import cv2
import numpy as np
from sbpl.motion_primitives import MotionPrimitives, dump_motion_primitives
from sbpl.utilities.map_drawing_utils import draw_robot
from sbpl.utilities.path_tools import pixel_to_world_centered, get_pixel_footprint, world_to_pixel_sbpl, blit


class EnvNAVXYTHETALAT_InitParms(sbpl._sbpl_module.EnvNAVXYTHETALAT_InitParms):
    pass


class EnvironmentNAVXYTHETALAT(sbpl._sbpl_module.EnvironmentNAVXYTHETALAT):

    def __init__(self, footprint, motion_primitives, costmap_data, env_params,
                 override_primitive_kernels=True, use_full_kernels=False):
        primitives_folder = tempfile.mkdtemp()
        try:
            dump_motion_primitives(motion_primitives, os.path.join(primitives_folder, 'primitives.mprim'))
            sbpl._sbpl_module.EnvironmentNAVXYTHETALAT.__init__(
                self,
                footprint,
                os.path.join(primitives_folder, 'primitives.mprim'),
                costmap_data,
                env_params,
                not override_primitive_kernels
            )
            if override_primitive_kernels:
                self._override_primitive_kernels(motion_primitives, footprint, use_full_kernels)

        finally:
            shutil.rmtree(primitives_folder)

    @staticmethod
    def create_from_config(environment_config_filename):
        return sbpl._sbpl_module.EnvironmentNAVXYTHETALAT(environment_config_filename)

    def get_motion_primitives(self):
        params = self.get_params()
        return MotionPrimitives(params.cellsize_m, params.numThetas, self.get_motion_primitives_list())

    def _override_primitive_kernels(self, motion_primitives, footprint, use_full_kernels):
        resolution = motion_primitives.get_resolution()
        print('Setting up motion primitive kernels..')
        for p in motion_primitives.get_primitives():

            primitive_start = pixel_to_world_centered(np.zeros((2,)), np.zeros((2,)), resolution)
            primitive_states = p.get_intermediate_states().copy()
            primitive_states[:, :2] += primitive_start

            full_cv_kernel_x = []
            full_cv_kernel_y = []
            for pose in primitive_states:
                kernel = get_pixel_footprint(pose[2], footprint, resolution)

                kernel_center = (kernel.shape[1] //  2, kernel.shape[0] //  2)
                kernel = np.where(kernel)

                px, py = world_to_pixel_sbpl(pose[:2], np.zeros((2,)), resolution)
                full_cv_kernel_x.append(kernel[1] + (px-kernel_center[0]))
                full_cv_kernel_y.append(kernel[0] + (py-kernel_center[1]))

            full_cv_kernel_x = np.hstack(full_cv_kernel_x)
            full_cv_kernel_y = np.hstack(full_cv_kernel_y)
            full_cv_kernel = np.column_stack((full_cv_kernel_x, full_cv_kernel_y)).astype(np.int32)

            row_view = np.ascontiguousarray(full_cv_kernel).view(
                np.dtype((np.void, full_cv_kernel.dtype.itemsize * full_cv_kernel.shape[1])))
            _, idx = np.unique(row_view, return_index=True)
            full_cv_kernel = np.ascontiguousarray(full_cv_kernel[idx])

            if use_full_kernels:
                self.set_primitive_collision_pixels(p.starttheta_c, p.motprimID, full_cv_kernel)
            else:
                min_x, max_x = np.amin(full_cv_kernel[:, 0]), np.amax(full_cv_kernel[:, 0])
                min_y, max_y = np.amin(full_cv_kernel[:, 1]), np.amax(full_cv_kernel[:, 1])

                temp_img = np.zeros((max_y - min_y+1, max_x - min_x+1), dtype=np.uint8)
                temp_img[full_cv_kernel[:, 1] - min_y, full_cv_kernel[:, 0] - min_x] = 255
                contours, _ = cv2.findContours(temp_img.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
                contour = contours[0].reshape(-1, 2)

                perimeter_kernel = np.column_stack((contour[:, 0] + min_x, contour[:, 1] + min_y)).astype(np.int32)

                self.set_primitive_collision_pixels(p.starttheta_c, p.motprimID, perimeter_kernel)

            # current_kernel = self.get_primitive_collision_pixels(p.starttheta_c, p.motprimID)
            #
            # min_x, max_x = np.amin(current_kernel[:, 0]), np.amax(current_kernel[:, 0])
            # min_y, max_y = np.amin(current_kernel[:, 1]), np.amax(current_kernel[:, 1])
            #
            # min_x_cv, max_x_cv = np.amin(full_cv_kernel[:, 0]), np.amax(full_cv_kernel[:, 0])
            # min_y_cv, max_y_cv = np.amin(full_cv_kernel[:, 1]), np.amax(full_cv_kernel[:, 1])
            #
            # min_x, max_x = min(min_x, min_x_cv), max(max_x, max_x_cv)
            # min_y, max_y = min(min_y, min_y_cv), max(max_y, max_y_cv)
            #
            # img = np.zeros((max_y-min_y+10, max_x - min_x+10, 3), dtype=np.uint8)
            # img[current_kernel[:, 1]-min_y, current_kernel[:, 0]-min_x, 1] = 255
            # img[full_cv_kernel[:, 1] - min_y, full_cv_kernel[:, 0] - min_x, 2] = 255
            # print(len(np.where((img[:, :, 1] > 0) & (img[:, :, 1] < 255))[0]))
            # img = np.flipud(img)
            # magnify = 8
            #
            # cv2.imshow("footpint",
            #            cv2.resize(img, dsize=(0, 0), fx=magnify, fy=magnify, interpolation=cv2.INTER_NEAREST))
            # cv2.waitKey(-1)

        print('Done.')