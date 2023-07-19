[property]
camera-mode={{ camera_mode }}
output-width={{ width }}
output-height={{ height }}
num-batch-buffers=1

[surface0]
# 3=PerspectivePerspective
projection-type=3
width={{ width }}
height={{ height }}
focal-length={{ focal_length }}
src-x0={{ cx }}
src-y0={{ cy }}
distortion={{ k0 }};{{ k1 }};{{ k2 }};{{ p0 }};{{ p1 }}
#src-fov=180
#top-angle=30
#bottom-angle=-30
# 0=cudaAddressModeClamp, 1=cudaAddressModeBorder
#cuda-address-mode=0

