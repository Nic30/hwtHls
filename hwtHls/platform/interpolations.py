from math import log2


# [TODO] downscale_width, upscale_width are useless
#       the are called to cancel each other and they need to be removed
def downscale_width(width):
    return log2(width)


def upscale_width(width):
    return pow(2.0, width)


def interpolate_area_linear(y_vals: dict, x):
    # linear vertical interpolation (y = a * x + b) for a
    # particular x over an array of discrete [x, y] data points
    lsort_x = list(y_vals.keys())
    lsort_x.sort()

    x0 = 0
    y0 = 0
    x1 = lsort_x[0]
    if x < x1:
        return y_vals[x1]

    y1 = 0
    x2 = lsort_x[-1]

    # [TODO]: bin search
    if x > x2:
        # is bigger than largest value in y_vals
        # interporalate by first and last point in y_vals
        y2 = y_vals[x2]
        x3 = lsort_x[-2]
        y3 = y_vals[x3]
        x3_r = upscale_width(x3)
        x2_r = upscale_width(x2)
        x_r = upscale_width(x)
        tmp = (x3_r - x_r) * y2 + (x_r - x2_r) * y3
        return tmp / (x3_r - x2_r)

    for x1 in lsort_x:
        # find point behind and after x and use them for interpolation
        y1 = y_vals[x1]

        if x < x1:
            x1_r = upscale_width(x1)
            x0_r = upscale_width(x0)
            x_r = upscale_width(x)
            tmp = (x1_r - x_r) * y0 + (x_r - x0_r) * y1
            return tmp / (x1_r - x0_r)

        x0 = x1
        y0 = y1

    return y1


def interpolate_area_2d(arr_2d, x, y):
    y_arr = []
    for x0, z_vals in arr_2d:
        y_arr_tmp = interpolate_area_linear(z_vals, y)
        y_arr.append(x0, y_arr_tmp)

    return interpolate_area_linear(y_arr, x)
