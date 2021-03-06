from typing import Optional
import os
import logging

from flask import Flask, render_template, send_from_directory, request

from stuff.search import Search
from stuff.client import StatefulClient
from stuff.maps import Charter, NO_IMAGE
from stuff.constants import (
    Category,
    Region,
)

from treasure_map.city_list import CITIES


def refine_city_name(location):
    """display User-friendly city name"""
    if location == 'newyork':  # does this have to capitalized
        loc = 'New York'
    elif location == 'washingtondc':
        loc = 'Washington D.C.'
    elif location == 'sanfrancisco':
        loc = 'San Francisco'
    else:
        loc = location
    return loc


def get_things(
        location: str,
        quantity: int,
        app_path: str,
        db_path: str,
        address: Optional[str] = None,
        proxies: Optional[dict] = None,
):
    """
    Get a list of Stuff using the client, and save a map of them.

    Return those Stuff objects in order to populate the view legend with a list of the things.
    """
    client = StatefulClient.new(
        db_path=db_path,
        search=Search(region=Region(location), category=Category.free),
        proxies=proxies,
    )
    client.populate_db(enrich_inventory=True)
    stuffs = client.select_stuff(location, quantity)
    charter = Charter(stuffs=stuffs, city=location, zoom=12, address=address)
    charter.create_map()

    map_path = os.path.join(app_path, 'templates', f'raw_map_{location}.html')
    charter.save_map(
        map_path,
        css_children={
            'bootstrap': os.path.join(app_path, 'static/css/style.css'),
        }
    )
    charter.save_map(map_path=map_path)
    things = []
    for stuff in stuffs:
        image = stuff.image_urls[0] if stuff.image_urls else NO_IMAGE
        things.append({
            'url': stuff.url,
            'image': image,
            'place': stuff.neighborhood or location,
            'title': stuff.title,
            'time': stuff.time.strftime("%-H:%-M %a %d/%m/%Y"),
        })
    return things


def create_app(config={}):
    app = Flask(__name__)

    debug = config.get("debug", False)
    proxy_host = config.get("proxy", None)
    db_path = config.get("db_path", "sqlite:///")

    proxies = {
        "https": "https://" + proxy_host,
        "http": "http://" + proxy_host,
    } if proxy_host else None

    logging.info("Launching app with config:")
    logging.info(config)

    app.config.update(DEBUG=debug)

    StatefulClient.new(db_path=db_path, proxies=proxies).setup()  # create db if doesn't exist

    @app.route('/favicon.ico')
    def favicon():
        """Serve favicon"""
        return send_from_directory(os.path.join(app.root_path, 'static'), 'ico/favicon.ico')

    @app.errorhandler(404)
    def page_not_found(e):
        """Render 404."""
        return render_template('404.html'), 404

    @app.route("/")
    def index():
        """Render index."""
        StatefulClient.new(
            db_path=db_path,
            proxies=proxies,
        ).setup()
        return render_template('index.html')

    @app.route("/cities")
    def list_cities():
        """Display valid city names."""
        cities_list = '<table>'
        cities_list += '<tr><th>User-Friendly Name</th><th>Valid for Url</th></tr>'
        for key, value in CITIES.items():
            cities_list += '<tr>'
            cities_list += ('<td>' + str(key) + '</td><td>' + str(value) + '</td>')
            cities_list += '</tr>'
        cities_list += '</table>'
        return cities_list

    @app.route('/<location>')
    def list_stuff(location):
        """Display listings"""
        things = get_things(location, 30, app.root_path, db_path, proxies=proxies)
        refined_loc = refine_city_name(location)
        return render_template('view.html', things=things, location=location, rlocation=refined_loc)

    def _serve_map(location, quantity, address=None):
        things = get_things(location, quantity, app.root_path, db_path, address=address, proxies=proxies)
        raw_file = f"raw_map_{location}.html"
        refined_location = refine_city_name(location)

        return render_template('map.html', location=refined_location, things=things, raw_file=raw_file)

    @app.route('/<location>/map')
    def show_map(location):
        return _serve_map(location, 30)

    @app.route('/<location>/map/<int:quantity>')
    def show_map_more(location, quantity):
        return _serve_map(location, quantity)

    @app.route('/address', methods=['POST'])
    def search_address():
        location = request.form['location']
        address = request.form['address']
        return _serve_map(location, 50, address=address)

    return app
