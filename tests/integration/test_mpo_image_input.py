# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Static MPO phone-photo intake and provider primary-image projection, no HTTP."""
from io import BytesIO
import hashlib
import unittest
from PIL import Image
from twinpulse_app.image_validation import decode_image, ImageValidationError
from twinpulse_provider import ImageInput
from twinpulse_provider.image_payload import image_payload


def mpo():
    output=BytesIO()
    Image.new('RGB',(6,5),'red').save(output,format='MPO',save_all=True,
                                    append_images=[Image.new('RGB',(6,5),'blue')])
    return output.getvalue()


class MpoInputTests(unittest.TestCase):
    def test_static_components_are_decoded_and_total_pixels_remain_bounded(self):
        raw=mpo()
        decoded=decode_image(raw,max_pixels=100)
        self.assertEqual((decoded.media_type,decoded.width,decoded.height),('image/jpeg',6,5))
        with self.assertRaisesRegex(ImageValidationError,'Total MPO pixel'):
            decode_image(raw,max_pixels=50)
        with self.assertRaises(ImageValidationError):
            decode_image(raw[:-30],max_pixels=100)

    def test_primary_jpeg_sent_and_original_input_stays_byte_exact(self):
        raw=mpo();digest=hashlib.sha256(raw).hexdigest()
        image=ImageInput('phone.jpg','image/jpeg',raw)
        mime,wire=image_payload(image)
        with Image.open(BytesIO(wire)) as opened:
            self.assertEqual(opened.format,'JPEG')
            self.assertEqual(opened.size,(6,5));opened.load()
        self.assertEqual(mime,'image/jpeg')
        self.assertEqual(hashlib.sha256(image.content).hexdigest(),digest)

    def test_standard_images_are_unchanged_on_provider_wire(self):
        output=BytesIO();Image.new('RGB',(6,5)).save(output,format='JPEG')
        raw=output.getvalue()
        self.assertEqual(image_payload(ImageInput('normal.jpg','image/jpeg',raw)),('image/jpeg',raw))


if __name__=='__main__':
    unittest.main()
