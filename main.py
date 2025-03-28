import os
import re
import random
import requests
import logging
from datetime import datetime
from typing import Optional, List, Dict, Tuple, Union
import tkinter as tk
from tkinter import filedialog, simpledialog, messagebox
from docx import Document
from dotenv import load_dotenv
import google.generativeai as genai
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('markdown_converter.log'),
        logging.StreamHandler()
    ]
)

class MarkdownConverter:
    """Converts text/docx files to enhanced Markdown with AI assistance."""

    def __init__(self):
        """Initialize the converter with default settings."""
        self.root = tk.Tk()
        self.root.withdraw()
        self.api_key = self.get_api_key()
        self.model = self.configure_gemini()
        self.nife_base_url = "https://nife.io"
        self.session = self._create_session()
        self.known_good_domains = [
            'wikipedia.org',
            'github.com',
            'stackoverflow.com',
            'developer.mozilla.org',
            'css-tricks.com',
            'digitalocean.com',
            'freecodecamp.org',
            'w3schools.com'
        ]
        self.max_content_length = 4000  # Max tokens for API calls
        self.request_timeout = 15  # Seconds for HTTP requests
        self.max_retries = 3  # Max retries for failed operations

    def _create_session(self) -> requests.Session:
        """Create and configure a requests session."""
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
        })
        return session

    def get_api_key(self) -> str:
        """Get and validate API key from environment or user input."""
        load_dotenv()
        api_key = os.getenv("GEMINI_API_KEY")

        if not api_key or len(api_key) < 30:
            api_key = simpledialog.askstring(
                "API Key Required",
                "Enter your Gemini API Key:",
                parent=self.root
            )

            if not api_key or len(api_key) < 30:
                messagebox.showerror("Error", "Invalid API key provided")
                self.root.destroy()
                raise ValueError("Invalid API key provided")

        return api_key

    def configure_gemini(self) -> genai.GenerativeModel:
        """Configure Gemini API with safety settings."""
        try:
            genai.configure(api_key=self.api_key)
            return genai.GenerativeModel(
                model_name="models/gemini-1.5-flash-latest",
                generation_config={
                    "temperature": 0.3,
                    "top_p": 1,
                    "top_k": 32,
                    "max_output_tokens": 4000,
                },
                safety_settings=[
                    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                ]
            )
        except Exception as e:
            logging.error(f"Failed to configure Gemini: {str(e)}")
            messagebox.showerror("Error", f"Failed to configure Gemini: {str(e)}")
            self.root.destroy()
            raise

    def select_file(self) -> str:
        """Select input file through GUI dialog."""
        file_path = filedialog.askopenfilename(
            title="Select a Text or Word Document",
            filetypes=[
                ("Text Files", "*.txt"),
                ("Word Documents", "*.docx"),
                ("All Files", "*.*")
            ]
        )
        if not file_path:
            logging.warning("No file selected")
            messagebox.showwarning("Warning", "No file selected")
            self.root.destroy()
            raise FileNotFoundError("No file selected")
        return file_path

    def read_file(self, file_path: str) -> str:
        """Read content from text or Word documents with multiple encoding attempts."""
        logging.info(f"Reading file: {file_path}")

        def read_text_file(encoding: str) -> Optional[str]:
            try:
                with open(file_path, 'r', encoding=encoding) as file:
                    return file.read()
            except UnicodeDecodeError:
                return None

        try:
            if file_path.lower().endswith('.docx'):
                doc = Document(file_path)
                return '\n'.join([para.text for para in doc.paragraphs if para.text.strip()])

            # Try multiple encodings for text files
            for encoding in ['utf-8', 'utf-16', 'latin-1']:
                content = read_text_file(encoding)
                if content is not None:
                    return content

            raise UnicodeDecodeError("Failed to decode file with any supported encoding")
        except Exception as e:
            logging.error(f"Error reading file {file_path}: {str(e)}")
            messagebox.showerror("Error", f"Error reading file: {str(e)}")
            raise

    def _call_gemini_api(self, prompt: str, max_retries: int = 3) -> str:
        """Helper method to call Gemini API with retry logic."""
        for attempt in range(max_retries):
            try:
                response = self.model.generate_content(prompt)
                if response.text:
                    return response.text.strip()
                raise ValueError("Empty response from API")
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                wait_time = (attempt + 1) * 2  # Exponential backoff
                logging.warning(f"API call failed (attempt {attempt + 1}), retrying in {wait_time} seconds...")
                time.sleep(wait_time)

        return ""  # Should never reach here

    def humanize_content(self, content: str) -> str:
        """Humanize the content to make it more engaging and natural."""
        logging.info("Humanizing content")

        truncated_content = content[:self.max_content_length]
        prompt = f"""Please humanize and enhance this content to make it more engaging, natural, and reader-friendly:

        {truncated_content}

        Guidelines:
        1. Maintain all key information and technical accuracy
        2. Make the tone conversational but professional
        3. Break up long paragraphs into digestible chunks
        4. Add transitions between ideas
        5. Include rhetorical questions where appropriate
        6. Use examples and analogies to clarify complex concepts
        7. Ensure the content flows naturally
        8. Keep the original meaning intact

        Output ONLY the enhanced content."""

        try:
            return self._call_gemini_api(prompt)
        except Exception as e:
            logging.warning(f"Error humanizing content: {str(e)}")
            messagebox.showwarning("Warning", f"Error humanizing content: {str(e)}")
            return content  # Fallback to original on error

    def generate_metadata(self, author_name: str, content: str) -> str:
        """Generate comprehensive metadata section."""
        logging.info("Generating metadata")
        today = datetime.now().strftime("%Y-%m-%d")
        truncated_content = content[:3000]

        prompt = f"""Based on this content, generate comprehensive metadata:
1. A compelling title
2. A 2-3 sentence description
3. 5-7 relevant keywords
4. Current date ({today})
5. 3-5 relevant tags
6. Author name ({author_name})
7. A hero image path

Content:
{truncated_content}

Format EXACTLY like this:

---
title: '[Generated Title]'
description: "[Generated description]"
keywords: [keyword1, keyword2, keyword3]
date: "{today}"
tags: [tag1, tag2, tag3]
hero: ./img/hero-image.jpg
author: {author_name}
---

Output ONLY this block."""

        try:
            return self._call_gemini_api(prompt)
        except Exception as e:
            logging.warning(f"Error generating metadata: {str(e)}")
            messagebox.showwarning("Warning", f"Error generating metadata: {str(e)}")
            return f"""---
title: 'Default Title'
description: "Default description"
keywords: [keyword1, keyword2]
date: "{today}"
tags: [general]
hero: ./img/default-hero.jpg
author: {author_name}
---"""

    def _fetch_with_retry(self, url: str, method: str = 'get', **kwargs) -> Optional[requests.Response]:
        """Helper method for HTTP requests with retry logic."""
        for attempt in range(self.max_retries):
            try:
                if method.lower() == 'get':
                    response = self.session.get(url, timeout=self.request_timeout, **kwargs)
                elif method.lower() == 'head':
                    response = self.session.head(url, timeout=self.request_timeout, **kwargs)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")

                if response.status_code < 400:
                    return response

                logging.warning(f"Attempt {attempt + 1}: HTTP {response.status_code} for {url}")
                if attempt == self.max_retries - 1:
                    return None

            except Exception as e:
                logging.warning(f"Attempt {attempt + 1}: Error fetching {url} - {str(e)}")
                if attempt == self.max_retries - 1:
                    return None

            time.sleep((attempt + 1) * 1)  # Linear backoff

        return None

    def get_nife_internal_link(self, content: str) -> Optional[str]:
        """Find the most relevant internal link from nife.io based on content using Gemini."""
        logging.info("Finding internal link from nife.io using Gemini")
        truncated_content = content[:2000]  # Use a portion of the content for the prompt

        prompt = f"""Given the following content, find the most relevant internal page URL from the website nife.io. If no highly relevant page is found, return the URL of the nife.io blog page: https://nife.io/blog/

Content:
{truncated_content}

Output ONLY the URL."""

        try:
            response = self._call_gemini_api(prompt)
            if response and response.startswith("https://nife.io"):
                # Basic validation to ensure it's a nife.io link
                return response.strip()
            else:
                logging.warning(f"Gemini did not return a valid nife.io link: {response}. Falling back to blog URL.")
                return f"{self.nife_base_url}/blog/"
        except Exception as e:
            logging.error(f"Error finding nife.io internal link using Gemini: {str(e)}. Falling back to blog URL.")
            return f"{self.nife_base_url}/blog/"

    def validate_external_link(self, url: str) -> bool:
        """Check if an external link is valid and accessible."""
        try:
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                return False

            # Skip checking for certain reliable domains
            if any(domain in parsed.netloc for domain in self.known_good_domains):
                return True

            # Try HEAD request first (faster)
            response = self._fetch_with_retry(url, method='head', allow_redirects=True)
            if response and response.status_code < 400:
                return True

            # If HEAD fails, try GET
            response = self._fetch_with_retry(url)
            return response is not None and response.status_code < 400

        except Exception as e:
            logging.warning(f"Error validating link {url}: {str(e)}")
            return False

    def generate_reliable_external_links(self, content: str) -> str:
        """Generate exactly 4 external links directly related to the content using Gemini."""
        logging.info("Generating 4 content-related external links")

        try:
            prompt = f"""Find 4 external links that are highly relevant to the content below. For each link, provide the URL and a concise (one-sentence) description explaining its relevance.

Content:
{content[:3000]}

Format the output as a markdown list:
- [Description of link](URL)

Only output the markdown list."""

            response = self._call_gemini_api(prompt)
            links = []
            for line in response.strip().split('\n'):
                match = re.match(r'^- \[(.*?)\]\((.*?)\)$', line)
                if match:
                    description = match.group(1)
                    url = match.group(2)
                    if self.validate_external_link(url):
                        links.append(f"- [{description}]({url})")
                    else:
                        logging.warning(f"Invalid or inaccessible external link found: {url}")

            if len(links) == 4:
                return "\n".join(links)
            else:
                logging.warning(f"Found {len(links)} valid content-related external links, expected 4. Using fallback links.")
                # Fallback to ensure we have some external links
                fallback_links = [
                    "- [Wikipedia](https://www.wikipedia.org) - General knowledge resource",
                    "- [Stack Overflow](https://stackoverflow.com) - Programming questions",
                    "- [MDN Web Docs](https://developer.mozilla.org) - Web development reference",
                    "- [GitHub](https://github.com) - Code repositories and documentation"
                ]
                return "\n".join(fallback_links[:4]) # Ensure we return at most 4

        except Exception as e:
            logging.error(f"Error generating content-related links: {str(e)}")
            # Fallback to basic known-good links on error
            return """- [Wikipedia](https://www.wikipedia.org) - General knowledge resource
- [Stack Overflow](https://stackoverflow.com) - Programming questions
- [MDN Web Docs](https://developer.mozilla.org) - Web development reference
- [GitHub](https://github.com) - Code repositories and documentation"""

    def generate_links(self, content: str) -> str:
        """Generate 5 links (1 internal from nife.io + 4 external related to content) with reliable validation."""
        logging.info("Generating links section")

        try:
            # Get internal link
            internal_link = self.get_nife_internal_link(content)
            internal_link_md = f"- [Related article on nife.io]({internal_link}) - Internal resource" if internal_link else ""

            # Get reliable external links related to content
            external_links = self.generate_reliable_external_links(content)

            # Combine them
            all_links = []
            if internal_link_md:
                all_links.append(internal_link_md)
            if external_links:
                all_links.extend(external_links.split('\n'))

            return "\n".join(all_links[:5]) # Ensure we return at most 5 links

        except Exception as e:
            logging.error(f"Error generating links: {str(e)}")
            # Ultimate fallback
            return """- [nife.io Blog](https://nife.io/blog/) - Internal resources
- [Wikipedia](https://www.wikipedia.org) - General knowledge
- [GitHub](https://github.com) - Code repositories
- [Stack Overflow](https://stackoverflow.com) - Programming help
- [MDN Web Docs](https://developer.mozilla.org) - Web reference"""

    def generate_images(self, content: str) -> List[Dict[str, str]]:
        """Generate 3 image tags with content-relevant alt text."""
        logging.info("Generating image suggestions")

        prompt = f"""Based on this content, suggest 3 relevant images that would enhance understanding:
{content[:2000]}

For each image provide:
1. A descriptive alt text (related to content)
2. A relevant filename (use format: 'topic-description.jpg')

Format each image suggestion as:
1. Alt: [description], File: [filename]
2. Alt: [description], File: [filename]
3. Alt: [description], File: [filename]

Output ONLY this numbered list."""

        try:
            response = self._call_gemini_api(prompt)
            images = []
            for line in response.strip().split('\n'):
                if line.startswith(('1.', '2.', '3.')):
                    parts = line.split('Alt:')[1].split(', File:')
                    alt_text = parts[0].strip()
                    filename = parts[1].strip() if len(parts) > 1 else f"image-{random.randint(1000,9999)}.jpg"
                    images.append({
                        'alt': alt_text,
                        'file': filename,
                        'tag': f'<img src="{{require(\'./img/{filename}\').default}}" alt="{alt_text}" width="600" height="350"/>\n<br/>'
                    })
            return images[:3]  # Ensure we return max 3 images
        except Exception as e:
            logging.error(f"Error generating images: {str(e)}")
            messagebox.showwarning("Warning", f"Error generating images: {str(e)}")
            return [
                {
                    'alt': 'Relevant image for article content',
                    'file': 'content-image-1.jpg',
                    'tag': '<img src={require(\'./img/content-image-1.jpg\').default} alt="Relevant image for article content" width="600" height="350"/>\n<br/>'
                },
                {
                    'alt': 'Illustration of main concept',
                    'file': 'concept-illustration.jpg',
                    'tag': '<img src={require(\'./img/concept-illustration.jpg\').default} alt="Illustration of main concept" width="600" height="350"/>\n<br/>'
                },
                {
                    'alt': 'Visual representation of data',
                    'file': 'data-visualization.jpg',
                    'tag': '<img src={require(\'./img/data-visualization.jpg\').default} alt="Visual representation of data" width="600" height="350"/>\n<br/>'
                }
            ]

    def distribute_elements(self, content: str, links: str, images: List[Dict[str, str]]) -> str:
        """Distribute links and images strategically throughout content."""
        logging.info("Distributing elements in content")

        paragraphs = [p for p in content.split('\n\n') if p.strip()]

        if not paragraphs:
            return content

        # Convert links to list items
        link_items = links.split('\n') if links else []
        image_items = images[:3]  # Use up to 3 images

        # Calculate positions for elements
        total_elements = len(link_items) + len(image_items)
        if total_elements == 0:
            return content

        # Create a list of all elements to insert (shuffled)
        all_elements = []
        if link_items:
            all_elements.extend([('link', item) for item in link_items])
        if image_items:
            all_elements.extend([('image', item) for item in image_items])
        random.shuffle(all_elements)

        # Calculate insertion points (spread evenly)
        section_size = len(paragraphs) // (total_elements + 1)
        insertion_points = [section_size * (i+1) for i in range(total_elements)]

        # Insert elements at calculated points
        for i, (element_type, element) in enumerate(all_elements):
            pos = min(insertion_points[i], len(paragraphs)-1)

            # Ensure we don't insert similar elements consecutively
            if i > 0:
                prev_element_type = all_elements[i-1][0]
                if element_type == prev_element_type:
                    pos = min(pos + 1, len(paragraphs)-1)

            if element_type == 'image':
                paragraphs.insert(pos, element['tag'])
            else:
                paragraphs.insert(pos, element)

        return '\n\n'.join(paragraphs)

    def convert_to_markdown(self) -> None:
        """Main conversion workflow with all features."""
        try:
            file_path = self.select_file()
            content = self.read_file(file_path)
            if not content:
                return

            # Get author name
            author_name = simpledialog.askstring(
                "Author Name",
                "Enter author name:",
                initialvalue="Anonymous",
                parent=self.root
            ) or "Anonymous"

            # Humanize the content first
            humanized_content = self.humanize_content(content)

            # Generate all components
            metadata = self.generate_metadata(author_name, humanized_content)
            images = self.generate_images(humanized_content)
            links = self.generate_links(humanized_content)

            # Process main content
            prompt = f"""Convert this humanized content into professional markdown:
{humanized_content[:self.max_content_length]}

Requirements:
1. Maintain original meaning but enhance readability
2. Use proper heading hierarchy
3. Format lists properly
4. Add code blocks when appropriate
5. Keep paragraphs concise
6. Preserve the humanized tone and flow

Output ONLY the formatted content."""

            formatted_content = self._call_gemini_api(prompt)
            if not formatted_content:
                raise ValueError("No content generated from markdown conversion")

            # Combine all components with strategic distribution
            main_content = self.distribute_elements(formatted_content, links, images)
            full_content = f"""{metadata}

{main_content}"""

            # Save with UTF-8 encoding
            output_path = os.path.splitext(file_path)[0] + ".md"
            try:
                with open(output_path, 'w', encoding='utf-8') as file:
                    file.write(full_content)
                logging.info(f"Successfully created Markdown file: {output_path}")
                messagebox.showinfo("Success", f"Markdown file successfully created:\n{output_path}")
            except Exception as e:
                logging.error(f"Failed to save file {output_path}: {str(e)}")
                messagebox.showerror("Error", f"Failed to save file: {str(e)}")

        except Exception as e:
            logging.error(f"Error during conversion: {str(e)}")
            messagebox.showerror("Error", f"Error during processing: {str(e)}")
        finally:
            self.root.destroy()

if __name__ == "__main__":
    try:
        converter = MarkdownConverter()
        converter.convert_to_markdown()
    except Exception as e:
        logging.error(f"Application error: {str(e)}")
        messagebox.showerror("Critical Error", f"The application encountered an error: {str(e)}")