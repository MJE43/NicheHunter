import os
import time
import csv
import tkinter as tk
from tkinter import ttk, messagebox
import aiohttp
import asyncio
from dotenv import load_dotenv
import folium
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError
from aiocache import cached

# Load environment variables
load_dotenv()

class BusinessLogic:
    """Handles the core business logic for finding and processing business data."""

    def __init__(self, api_key):
        """
        Initialize the BusinessLogic class.

        Args:
            api_key (str): The API key for accessing Google Maps API.
        """
        self.api_key = api_key
        self.geolocator = Nominatim(user_agent="business_niche_finder")

    def get_coordinates(self, place_name):
        """
        Get coordinates for a given place name.

        Args:
            place_name (str): Name of the place to geocode.

        Returns:
            str: Latitude and longitude as a string, or None if geocoding fails.
        """
        try:
            location = self.geolocator.geocode(place_name)
            if location:
                return f"{location.latitude},{location.longitude}"
        except (GeocoderTimedOut, GeocoderServiceError) as e:
            print(f"Geocoding error: {e}")
        return None

    def build_url(self, location, radius, business_type=None, next_page_token=None):
        """
        Build the URL for the Google Places API request.

        Args:
            location (str): Latitude and longitude.
            radius (int): Search radius in meters.
            business_type (str, optional): Type of business to search for.
            next_page_token (str, optional): Token for the next page of results.

        Returns:
            str: The constructed URL.
        """
        base_url = f'https://maps.googleapis.com/maps/api/place/nearbysearch/json?location={location}&radius={radius}&key={self.api_key}'
        if business_type:
            base_url += f'&type={business_type}'
        if next_page_token:
            base_url += f'&pagetoken={next_page_token}'
        return base_url

    @cached(ttl=3600)
    async def fetch(self, session, url):
        """
        Fetch data from the given URL using aiohttp.

        Args:
            session (aiohttp.ClientSession): The aiohttp session.
            url (str): The URL to fetch data from.

        Returns:
            dict: The JSON response.
        """
        async with session.get(url) as response:
            return await response.json()

    async def get_business_details(self, session, place_id, filters):
        """
        Get detailed information about a business and apply filters.

        Args:
            session (aiohttp.ClientSession): The aiohttp session.
            place_id (str): The Google Places ID of the business.
            filters (dict): Dictionary of filter settings.

        Returns:
            dict: Business details if it passes all filters, None otherwise.
        """
        details_url = f'https://maps.googleapis.com/maps/api/place/details/json?place_id={place_id}&fields=name,formatted_phone_number,website,formatted_address,types,business_status,reviews&key={self.api_key}'
        try:
            result = await self.fetch(session, details_url)
            result = result.get('result', {})
        except Exception as e:
            print(f"Error fetching business details: {e}")
            return None

        # Apply filters
        if filters['without_website'] and 'website' in result:
            return None
        if filters['operational'] and result.get('business_status') != 'OPERATIONAL':
            return None
        if filters['has_phone'] and 'formatted_phone_number' not in result:
            return None
        if filters['has_recent_reviews'] and not (result.get('reviews') and any(review['time'] > time.time() - 30*24*60*60 for review in result['reviews'])):
            return None
        if filters['has_any_reviews'] and not result.get('reviews'):
            return None
        
        return {
            'name': result['name'],
            'phone': result.get('formatted_phone_number', 'N/A'),
            'website': result.get('website', 'N/A'),
            'address': result.get('formatted_address', 'N/A'),
            'industry': ', '.join(result.get('types', [])),
            'business_status': result.get('business_status', 'N/A')
        }

    async def find_businesses(self, location, radius, business_type, filters, status_callback):
        """
        Find businesses based on given criteria and filters.

        Args:
            location (str): Latitude and longitude.
            radius (int): Search radius in meters.
            business_type (str): Type of business to search for.
            filters (dict): Dictionary of filter settings.
            status_callback (function): Callback to update status in GUI.

        Returns:
            list: List of businesses that match the criteria and pass the filters.
        """
        businesses = []
        next_page_token = None
        page = 1

        async with aiohttp.ClientSession() as session:
            while True:
                status_callback(f"Searching page {page}...")
                url = self.build_url(location, radius, business_type, next_page_token)
                try:
                    json_response = await self.fetch(session, url)
                except Exception as e:
                    print(f"Error fetching businesses: {e}")
                    break

                if 'results' not in json_response:
                    break

                tasks = [self.get_business_details(session, result['place_id'], filters) for result in json_response['results']]
                results = await asyncio.gather(*tasks)

                for business in results:
                    if business:
                        businesses.append(business)

                next_page_token = json_response.get('next_page_token')
                if not next_page_token:
                    break
                await asyncio.sleep(2)
                page += 1

        return businesses

    @staticmethod
    def write_to_csv(businesses, filename='businesses.csv'):
        """
        Write business data to a CSV file.

        Args:
            businesses (list): List of dictionaries containing business data.
            filename (str, optional): Name of the output CSV file. Defaults to 'businesses.csv'.
        """
        fieldnames = ['name', 'phone', 'website', 'address', 'industry', 'business_status']
        try:
            with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                for business in businesses:
                    writer.writerow(business)
            print(f"Data written to {filename}")
        except IOError as e:
            print(f"Error writing to CSV: {e}")

class BusinessNicheFinderGUI:
    """Handles the GUI for the Business Niche Finder application."""

    def __init__(self, master):
        """
        Initialize the GUI.

        Args:
            master: The root window for the GUI.
        """
        self.master = master
        master.title("Business Niche Finder")

        self.business_logic = BusinessLogic(os.getenv('API_KEY'))

        self.create_widgets()

    def create_widgets(self):
        """Create and arrange widgets in the GUI."""
        # Create map (placeholder for now)
        ttk.Label(self.master, text="Map Placeholder").grid(row=0, column=0, columnspan=2)

        # Business Type dropdown
        self.business_types = ["restaurant", "spa", "electrician", "roofing_contractor", "painter", "locksmith", "accounting", "plumber"]
        ttk.Label(self.master, text="Business Type").grid(row=1, column=0)
        self.type_var = tk.StringVar()
        self.type_dropdown = ttk.Combobox(self.master, textvariable=self.type_var, values=self.business_types)
        self.type_dropdown.grid(row=1, column=1)
        self.type_dropdown.set("plumber")

        # Filters
        self.without_website_var = tk.BooleanVar()
        ttk.Checkbutton(self.master, text="Without websites", variable=self.without_website_var).grid(row=2, column=0)

        self.operational_var = tk.BooleanVar()
        ttk.Checkbutton(self.master, text="Operational", variable=self.operational_var).grid(row=2, column=1)

        self.has_phone_var = tk.BooleanVar()
        ttk.Checkbutton(self.master, text="Has Phone Number", variable=self.has_phone_var).grid(row=3, column=0)

        self.has_recent_reviews_var = tk.BooleanVar()
        ttk.Checkbutton(self.master, text="Has Recent Reviews", variable=self.has_recent_reviews_var).grid(row=3, column=1)

        self.has_any_reviews_var = tk.BooleanVar()
        ttk.Checkbutton(self.master, text="Has Any Reviews", variable=self.has_any_reviews_var).grid(row=4, column=0)

        # Location and radius inputs
        ttk.Label(self.master, text="Location").grid(row=5, column=0)
        self.location_entry = ttk.Entry(self.master)
        self.location_entry.grid(row=5, column=1)
        self.location_entry.insert(0, "Philadelphia")

        ttk.Label(self.master, text="Radius (miles)").grid(row=6, column=0)
        self.radius_entry = ttk.Entry(self.master)
        self.radius_entry.grid(row=6, column=1)
        self.radius_entry.insert(0, "6")

        # Search button
        ttk.Button(self.master, text="Search", command=self.search).grid(row=7, column=0, columnspan=2)

        # Status label
        self.status_var = tk.StringVar()
        self.status_label = ttk.Label(self.master, textvariable=self.status_var)
        self.status_label.grid(row=8, column=0, columnspan=2)

    def search(self):
        """Perform the business search based on user inputs."""
        location = self.business_logic.get_coordinates(self.location_entry.get())
        if not location:
            messagebox.showerror("Error", "Failed to geocode the location.")
            return

        try:
            radius = int(float(self.radius_entry.get()) * 1609.34)  # Convert miles to meters
        except ValueError:
            messagebox.showerror("Error", "Invalid radius. Please enter a number.")
            return

        filters = {
            'without_website': self.without_website_var.get(),
            'operational': self.operational_var.get(),
            'has_phone': self.has_phone_var.get(),
            'has_recent_reviews': self.has_recent_reviews_var.get(),
            'has_any_reviews': self.has_any_reviews_var.get()
        }

        self.status_var.set("Searching...")
        self.master.update_idletasks()

        asyncio.run(self.async_search(location, radius, filters))

    async def async_search(self, location, radius, filters):
        """Asynchronous search for businesses."""
        businesses = await self.business_logic.find_businesses(
            location, radius, self.type_var.get(), filters, self.update_status
        )

        if businesses:
            self.business_logic.write_to_csv(businesses)
            self.status_var.set(f"Found {len(businesses)} businesses. Data written to businesses.csv")
        else:
            self.status_var.set("No businesses found based on your criteria.")

    def update_status(self, message):
        """Update the status message in the GUI."""
        self.status_var.set(message)
        self.master.update_idletasks()

if __name__ == '__main__':
    root = tk.Tk()
    app = BusinessNicheFinderGUI(root)
    root.mainloop()