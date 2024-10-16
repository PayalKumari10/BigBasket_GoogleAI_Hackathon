import os
import configparser
import PIL
from PIL import Image
from typing import Any, List, Optional, Literal
from pydantic import BaseModel, Field
import google.generativeai as genai
import vertexai
from vertexai.preview.vision_models import ImageGenerationModel, GeneratedImage
from vertexai.preview.vision_models import Image as VertexImage

# Load configuration
config = configparser.ConfigParser()
config.read('config.ini')

api_key = config['credentials']['gemini_api_key']
proj_id = config['credentials']['gcp_project_id']
info = {"PROJECT_ID": proj_id, "LOCATION": "us-central1", "API_KEY": api_key}

# Create directories for temporary and output images if they do not exist
os.makedirs('images/temp', exist_ok=True)
os.makedirs('images/output', exist_ok=True)

class BannerGenerator(BaseModel):
    """Class responsible for generating banners using generative models."""

    CONFIGS: dict
    topic: str
    images: List[str] | None = Field(default=None)
    aspect_ratio: Optional[Literal["1:1", "9:16", "16:9", "4:3", "3:4"]] = None  # Added aspect_ratio attribute
    text_model: str = "gemini-1.5-flash"
    image_model: str = "imagen-3.0-generate-001"
    edit_model: str = "imagegeneration@006"
    pm: Any = None
    im: Any = None
    em: Any = None
    text_v0: str = None
    text_v1: str = None
    text_v2: str = None
    text_v3: str = None
    img_response_v1: Any = None
    img_response_v2: Any = None
    img_response_v3: Any = None
    launch_state: bool = False

    def __launch(self):
        """Launches the generative models and sets up environment."""
        if not self.launch_state:
            vertexai.init(project=self.CONFIGS['PROJECT_ID'], location=self.CONFIGS['LOCATION'])
            genai.configure(api_key=self.CONFIGS['API_KEY'])
            self.pm = genai.GenerativeModel(self.text_model)
            self.im = ImageGenerationModel.from_pretrained(self.image_model)
            self.em = ImageGenerationModel.from_pretrained(self.edit_model)
            self.launch_state = True
            print("Model Launch successful!")

    def load_images(self) -> List[PIL.Image.Image]:
        """Loads images from file paths provided in the `images` attribute."""
        self.__launch()
        loaded_images = []

        for image_path in self.images:
            img = PIL.Image.open(image_path)
            if img.mode == 'RGBA':
                img = img.convert('RGB')  # Convert to RGB if needed
            loaded_images.append(img)

        return loaded_images

    def extract_image_information(self) -> str:
        """Extracts information from images using the generative text model."""
        images = self.load_images()
        extraction_prompt = '''Examine the set of images to extract information about the product (name, logo) in less than 80 words.'''
        model_input = [extraction_prompt] + images
        response = self.pm.generate_content(model_input)
        print("Attached images examined!")
        return response.text

    def extract_information(self) -> None:
        """Extracts information from the given topic and images using a detailed analysis."""
        self.__launch()

        out_text = f"""Deep analyze text from retail advertising, marketing psychology, and thoroughly researched marketing studies perspective: {self.topic}
        Extract the following information:
        0. Product: Product name, brand and supplier, logo, tagline, size, packaging if available
        1. Objective: 1 word for primary goal of the banner. Example - Awareness, Engagement, Conversion, Branding
        2. Festival: Event or occasion it may be tied to. Example - Christmas, Diwali, Black Friday, Summer Sale, New Year, Generic
        3. Headline: Suggest a main text that captures attention. Example - Discover [product] for [festival], Shop now and save!, Limited time offer, Innovate your life with [product]
        4. Subheadline: Optional additional supporting information to clarify the offer. Example - Get 50% off until [date], Exclusive deal for festive season, Hurry offer ends soon
        5. CTA: Add a call to action. Example - Buy now, Shop the collection, Discover More, Sign up today
        6. Color Scheme: Use color palette based on audience, occasion, or product tone. Example - Red & Gold (Festive, Urgency), Blue & White (Trust, Calm), Green & Brown (Eco-friendly, Natural), Black & White (Elegant, Minimal)
        7. Promotional offer: Suggest 1 best promotional offer. Example - MAX ₹99 OFF, UP TO 60% OFF, UNDER ₹999, MIN ₹10 OFF, MIN 20% OFF, STARTS @₹99, FLAT ₹100 OFF, FLAT 20% OFF, ₹499 STORE, BUY 2 GET 1 FREE
        8. Background color gradient: Dynamic color generation to match overall look and feel
        9. Background theme: Festival oriented or generic if no festival
        """
        self.text_v0 = self.pm.generate_content(out_text).text

        # Information consolidation
        out_text = f"Respond concisely and summarize in Python dictionary format only this: {self.text_v0}"
        if self.images:
            image_info = self.extract_image_information()
            out_text += ' Product insights: ' + image_info
            print(f"Product insights: {image_info}")

        self.text_v1 = self.pm.generate_content(out_text).text[9:-5]

        # Scrapper to ensure data integrity and consistency
        out_text = f"Respond concisely by scrapping all unavailable information in Python dictionary format only this: {self.text_v1}"
        self.text_v2 = self.pm.generate_content(out_text).text

        print("Information collection complete!")

    def create_text_prompt(self) -> None:
        """Creates a text prompt based on the extracted information."""
        out_text = f"""Task: Fill in the values in this json: {self.text_v2}
        Guidelines:
        1. It will be used to generate an ads banner.
        2. Ensure it has all details pair-wise meticulously captured.
        3. All unknown/missing/unprovided variables are replaced with the attributes of the most probable shopper for that product.
        4. Recheck and identify all ambiguity or any text that leads to uncertainty.
        5. Replace all uncertainty with targeted values that make the most sense for the given product.
        6. Quantify everything possible, like high, medium, and lows to percentage values based on marketing and psychometric research studies.
        7. All KPIs and qualitative measures are to be used subcontextually only. Remove any details about statistical testing or names of any performance KPIs.
        8. Avoid sentences and use only necessary keywords.
        9. Remove all redundant key-value pairs.
        """
        self.text_v3 = self.pm.generate_content(out_text).text
        print("Information processed!")

    def generate_image(self) -> str:
        """Generates an image based on the given prompt and saves it in images/temp/."""
        prompt = f"""Realistic, subcontextually implied qualitative attributes inspired, excellent image quality ad capturing every detail in json:{self.text_v3}"""

        # Adding the aspect ratio parameter to the image generation
        if self.aspect_ratio:
            self.img_response_v1 = self.im.generate_images(prompt=prompt, aspect_ratio=self.aspect_ratio)
        else:
            self.img_response_v1 = self.im.generate_images(prompt=prompt)

        # Save the generated image to images/temp/
        temp_img_path = 'images/temp/temp.jpg'
        if os.path.exists(temp_img_path):
            os.remove(temp_img_path)
        self.img_response_v1.images[0].save(temp_img_path)

        print("Image v1 generated!")
        return temp_img_path

    def identify_lags(self) -> str:
        """Identifies quality issues in the generated image and provides suggestions for improvement."""
        prompt = f"""Be direct. Quality check the banner out of 10 on:
        1. Promotional offer present as per instructions below
        2. Ensure ALL texts pass grammatical checks
        3. Color pallette as per instructions below
        4. Occassion or festival theme is present as per instructions below

        ONLY USE INFORMATION FROM {self.text_v3}. Don't DO NOT make up colors, promo or occasion. Make sure the promo and color pallete is followed as per above instructions.

        Precisely point out errors and corresponding actions to fix the image where score is below 8.
        Do not output anything about elements that need no change.
        """
        temp_img_path = 'images/temp/temp.jpg'
        response = self.pm.generate_content([prompt, PIL.Image.open(temp_img_path)])
        print(f'Lags identified: {response.text}')
        return response.text

    def fix_image(self, retest: bool = False) -> str:
        """Attempts to fix the identified lags in the generated image and saves it."""
        prompt = f'Realistic, subcontextually implied qualitative attributes inspired, excellent image quality ad by: {self.identify_lags()}'
        temp_img_path = 'images/temp/temp.jpg'

        base_image = VertexImage.load_from_file(location=temp_img_path)
        self.img_response_v2 = self.em.edit_image(
            base_image=base_image,
            prompt=prompt,
            edit_mode="inpainting-insert",
            mask_mode="background"
        )
        self.img_response_v2.images[0].save(temp_img_path)
        print("Image v2 generated!")

        if retest:
            prompt = f'Realistic, subcontextually implied qualitative attributes inspired, excellent image quality ad edit by: {self.identify_lags()}'
            self.img_response_v3 = self.em.edit_image(
                base_image=VertexImage.load_from_file(location=temp_img_path),
                prompt=prompt,
                edit_mode="inpainting-insert",
                mask_mode="background"
            )
            self.img_response_v3.images[0].save(temp_img_path)
            print("Image v3 generated!")

        # Save final image to output directory with a name corresponding to the topic
        output_filename = ''.join(e for e in self.topic if e.isalnum() or e == ' ')
        output_filename = output_filename[:50].strip().replace(' ', '_') + ".jpg"
        output_img_path = os.path.join('images/output', output_filename)
        self.img_response_v2.images[0].save(output_img_path)
        print(f"Final image saved as: {output_img_path}")

        return output_img_path

    def execute(self, QC=False) -> str:
        """Executes the entire workflow to generate and refine the banner."""
        self.extract_information()
        self.create_text_prompt()
        self.generate_image()
        final_image_path = self.fix_image(retest=QC)
        return final_image_path