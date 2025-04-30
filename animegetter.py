import requests
import json
import time
import os
from tqdm import tqdm

class BaseAnimeExtractor:
    """Base class for anime data extraction"""
    
    def __init__(self):
        """Initialize the base extractor"""
        pass
        
    def save_data_to_json(self, data, filepath):
        """
        Save data to a JSON file.
        
        Args:
            data: Data to save (list or dict)
            filepath (str): Path to save the JSON file
            
        Returns:
            str: Path to the saved file
        """
        os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            
        print(f"Data saved to {filepath}")
        return filepath


class MALExtractor(BaseAnimeExtractor):
    """
    A class to extract anime and user data from MyAnimeList's official API.
    Requires a client ID for the official MyAnimeList API.
    """
    
    def __init__(self, client_id):
        """
        Initialize the MAL extractor.
        
        Args:
            client_id (str): Your MyAnimeList API client ID
        """
        super().__init__()
        if not client_id:
            raise ValueError("A client ID is required for the MyAnimeList API")
            
        self.client_id = client_id
        self.headers = {'X-MAL-CLIENT-ID': client_id}
        self.base_url = 'https://api.myanimelist.net/v2'
        self.request_count = 0
        
    def _handle_rate_limit(self):
        """Handle rate limiting for MyAnimeList API"""
        self.request_count += 1
        if self.request_count >= 20:
            time.sleep(3)
            self.request_count = 0
    
    def get_anime_recommendations(self, anime_ids):
        """
        Get recommendations for a list of anime IDs from the official MAL API.
        
        Args:
            anime_ids (list): List of anime IDs to get recommendations for
            
        Returns:
            dict: Dictionary mapping anime IDs to their recommendations
        """
        if not anime_ids:
            return {}
            
        # Initialize recommendations with empty lists for all anime IDs
        recommendations = {anime_id: [] for anime_id in anime_ids}
        
        print(f"Retrieving recommendations for {len(anime_ids)} anime from MAL API...")
        
        for anime_id in tqdm(anime_ids, desc="Fetching recommendations from MAL API"):
            url = f"{self.base_url}/anime/{anime_id}"
            params = {'fields': 'recommendations'}
            
            self._handle_rate_limit()
            
            try:
                response = requests.get(url, headers=self.headers, params=params)
                response.raise_for_status()
                data = response.json()
                
                recommendations[anime_id] = data.get('recommendations', [])
                
            except requests.RequestException as e:
                print(f"Error retrieving recommendations for anime {anime_id}: {e}")
                # Handle rate limiting errors
                if hasattr(response, 'status_code') and response.status_code == 429:
                    print("Rate limit hit. Waiting 60 seconds before retrying...")
                    time.sleep(60)
                    # Try again after waiting
                    try:
                        response = requests.get(url, headers=self.headers, params=params)
                        if response.status_code == 200:
                            data = response.json()
                            recommendations[anime_id] = data.get('recommendations', [])
                    except:
                        pass  # If it fails again, just continue
            
            time.sleep(0.5)  # Rate limiting between requests
        
        print(f"Successfully retrieved recommendations for {len(recommendations)} anime")
        return recommendations
    
    def get_anime_list(self, limit=500, use_rankings=True, fetch_special_fields=True, special_fields_to_fetch=None):
        """
        Get a list of anime with ratings from MyAnimeList's official API.
        
        Args:
            limit (int): Maximum number of anime to retrieve
            use_rankings (bool): Whether to use the rankings endpoint
            fetch_special_fields (bool): Whether to fetch special fields
            special_fields_to_fetch (list): List of specific special fields to fetch
            
        Returns:
            list: List of anime data dictionaries
        """
        # All available special fields that need separate API calls
        all_special_fields = ['pictures', 'background', 'related_anime', 'related_manga', 
                             'recommendations', 'statistics']
        
        # Determine which special fields to fetch
        if special_fields_to_fetch is None:
            special_fields_to_fetch = all_special_fields.copy() if fetch_special_fields else []
        else:
            # Validate the requested fields
            special_fields_to_fetch = [f for f in special_fields_to_fetch if f in all_special_fields]
        
        all_anime = []
        offset = 0
        remaining = limit
        
        print(f"Retrieving up to {limit} anime titles using official MAL API...")
        
        # First pass: Get basic anime data with all standard fields
        while remaining > 0:
            batch_size = min(100, remaining)  # API typically limits to 100 per request
            
            # Standard fields to fetch for all anime
            fields = ('id,title,main_picture,alternative_titles,start_date,end_date,synopsis,mean,'
                     'rank,popularity,num_list_users,num_scoring_users,genres,media_type,status,num_episodes,'
                     'start_season,broadcast,source,average_episode_duration,rating,studios')
            
            # Determine which endpoint to use
            if use_rankings:
                url = f"{self.base_url}/anime/ranking"
                params = {
                    'ranking_type': 'all',  # Ensures we get anime with ratings
                    'limit': batch_size,
                    'offset': offset,
                    'fields': fields
                }
            else:
                # Alternative method using search with a blank query to get all anime
                url = f"{self.base_url}/anime"
                params = {
                    'q': '',  # Empty query to get all anime
                    'limit': batch_size,
                    'offset': offset,
                    'fields': fields
                }
            
            # Track API requests to respect rate limits
            self._handle_rate_limit()
            
            try:
                response = requests.get(url, headers=self.headers, params=params)
                response.raise_for_status()
                data = response.json()
                
                # Extract anime nodes
                batch_anime = [item['node'] for item in data.get('data', [])]
                
                # Only include anime that have a mean rating if that's important
                batch_anime = [anime for anime in batch_anime if anime.get('mean') is not None]
                
                if not batch_anime:
                    break  # No more results with ratings
                    
                all_anime.extend(batch_anime)
                
                offset += len(batch_anime)
                remaining -= len(batch_anime)
                
                # Check if we've reached the end of available data
                if 'next' not in data.get('paging', {}):
                    break
                    
                # Rate limiting: wait to avoid hitting API limits
                time.sleep(1)
                
            except requests.RequestException as e:
                print(f"Error retrieving anime data: {e}")
                # Check if we hit rate limits
                if hasattr(response, 'status_code') and response.status_code == 429:
                    print("Rate limit hit. Waiting 60 seconds before retrying...")
                    time.sleep(60)
                else:
                    # Wait longer on error before retrying
                    time.sleep(5)
                continue
        
        # Skip second pass if not requested or no special fields to fetch
        if not special_fields_to_fetch:
            print(f"Successfully retrieved {len(all_anime)} anime titles with basic data.")
            return all_anime
        
        # Second pass: Get special fields for each anime (these require individual requests)
        print(f"Fetching additional data fields: {', '.join(special_fields_to_fetch)}")
        enriched_anime = []
        
        for anime in tqdm(all_anime, desc="Fetching detailed anime data"):
            anime_id = anime['id']
            
            # Fetch all special fields in a single request
            url = f"{self.base_url}/anime/{anime_id}"
            params = {
                'fields': ','.join(special_fields_to_fetch)
            }
            
            # Handle rate limiting
            self._handle_rate_limit()
            
            try:
                response = requests.get(url, headers=self.headers, params=params)
                response.raise_for_status()
                detailed_data = response.json()
                
                # Merge the detailed data with the base anime data
                for field in special_fields_to_fetch:
                    if field in detailed_data:
                        anime[field] = detailed_data[field]
                
            except requests.RequestException as e:
                print(f"Error retrieving details for anime {anime_id}: {e}")
                # Handle rate limits
                if hasattr(response, 'status_code') and response.status_code == 429:
                    print("Rate limit hit. Waiting 60 seconds before retrying...")
                    time.sleep(60)
                    # Try again after waiting
                    try:
                        response = requests.get(url, headers=self.headers, params=params)
                        response.raise_for_status()
                        detailed_data = response.json()
                        
                        for field in special_fields_to_fetch:
                            if field in detailed_data:
                                anime[field] = detailed_data[field]
                    except:
                        pass  # If it fails again, just continue
            
            enriched_anime.append(anime)
            # Rate limiting between requests
            time.sleep(0.5)
        
        print(f"Successfully retrieved {len(enriched_anime)} anime titles with all requested fields.")
        return enriched_anime
    
    def get_user_anime_list(self, username, limit=1000):
        """
        Get a user's anime list including their ratings from the official API.
        
        Args:
            username (str): MyAnimeList username
            limit (int): Maximum number of anime to retrieve from user's list
            
        Returns:
            list: User's anime list data
        """
        url = f"{self.base_url}/users/{username}/animelist"
        params = {
            'fields': 'list_status',
            'limit': 100,  # API typically limits to 100 per request
            'status': 'completed,watching,on_hold,dropped,plan_to_watch'
        }
        
        all_user_anime = []
        offset = 0
        remaining = limit
        
        print(f"Retrieving anime list for user '{username}'...")
        
        while remaining > 0:
            batch_size = min(100, remaining)
            params['limit'] = batch_size
            params['offset'] = offset
            
            # Handle rate limiting
            self._handle_rate_limit()
            
            try:
                response = requests.get(url, headers=self.headers, params=params)
                response.raise_for_status()
                data = response.json()
                
                batch_data = data.get('data', [])
                if not batch_data:
                    break  # No more results
                    
                # Extract only relevant information
                for item in batch_data:
                    anime_id = item['node']['id']
                    status = item['list_status']
                    
                    # Add username to associate this entry with the user
                    status['username'] = username
                    status['anime_id'] = anime_id
                    all_user_anime.append(status)
                
                offset += len(batch_data)
                remaining -= len(batch_data)
                
                # Check if we've reached the end of available data
                if 'next' not in data.get('paging', {}):
                    break
                    
                # Rate limiting
                time.sleep(1)
                
            except requests.RequestException as e:
                print(f"Error retrieving user anime list: {e}")
                if hasattr(response, 'status_code') and response.status_code == 429:
                    print("Rate limit hit. Waiting 60 seconds before retrying...")
                    time.sleep(60)
                else:
                    # Wait longer on error before retrying
                    time.sleep(5)
                continue
        
        print(f"Retrieved {len(all_user_anime)} anime entries for user '{username}'")
        return all_user_anime
    
    def get_multiple_users(self, usernames, limit_per_user=1000):
        """
        Get anime lists for multiple users from MAL API.
        
        Args:
            usernames (list): List of MyAnimeList usernames
            limit_per_user (int): Maximum number of anime to retrieve per user
            
        Returns:
            dict: Dictionary with username keys and user anime list values
        """
        all_user_data = {}
        
        for username in tqdm(usernames, desc="Retrieving user data"):
            user_anime = self.get_user_anime_list(username, limit=limit_per_user)
            all_user_data[username] = user_anime
            # More aggressive rate limiting between users
            time.sleep(2)
            
        print(f"Successfully retrieved data for {len(usernames)} users")
        return all_user_data


class JikanExtractor(BaseAnimeExtractor):
    """
    A class to extract anime and user data from the unofficial Jikan API.
    No API key required.
    """
    
    def __init__(self):
        """Initialize the Jikan extractor"""
        super().__init__()
        self.base_url = 'https://api.jikan.moe/v4'
    
    def _handle_rate_limit(self):
        """Handle rate limiting for Jikan API"""
        time.sleep(0.4)  # Jikan has a limit of ~3 requests per second
    
    def get_anime_recommendations(self, anime_ids):
        """
        Get recommendations for a list of anime IDs from the Jikan API.
        
        Args:
            anime_ids (list): List of anime IDs to get recommendations for
            
        Returns:
            dict: Dictionary mapping anime IDs to their recommendations (in MAL format)
        """
        if not anime_ids:
            return {}
            
        # Initialize recommendations with empty lists for all anime IDs
        recommendations = {anime_id: [] for anime_id in anime_ids}
        
        print(f"Retrieving recommendations for {len(anime_ids)} anime from Jikan API...")
        
        for anime_id in tqdm(anime_ids, desc="Fetching recommendations from Jikan API"):
            url = f"{self.base_url}/anime/{anime_id}/recommendations"
            
            self._handle_rate_limit()
            
            try:
                response = requests.get(url)
                
                if response.status_code == 200:
                    data = response.json()
                    jikan_recs = data.get('data', [])
                    recommendations[anime_id] = self._convert_to_mal_format(jikan_recs)
                else:
                    print(f"Error status {response.status_code} for anime {anime_id} from Jikan")
                
            except requests.RequestException as e:
                print(f"Error retrieving recommendations for anime {anime_id} from Jikan: {e}")
            
            time.sleep(0.4)  # Rate limiting between requests
        
        print(f"Successfully retrieved recommendations for {len(recommendations)} anime")
        return recommendations
    
    def _convert_to_mal_format(self, jikan_recs):
        """Convert Jikan API response format to match MAL API format"""
        mal_format_recs = []
        
        for rec in jikan_recs:
            mal_format_recs.append({
                'node': {
                    'id': rec['entry']['mal_id'],
                    'title': rec['entry']['title'],
                    'main_picture': {
                        'medium': rec['entry'].get('images', {}).get('jpg', {}).get('image_url', ''),
                        'large': rec['entry'].get('images', {}).get('jpg', {}).get('large_image_url', '')
                    }
                },
                'num_recommendations': rec.get('votes', 0)
            })
        
        return mal_format_recs
    
    def get_anime_list(self, limit=500, page_size=25, fetch_special_fields=True, special_fields_to_fetch=None):
        """
        Get a list of anime with ratings from the Jikan API.
        
        Args:
            limit (int): Maximum number of anime to retrieve
            page_size (int): Number of anime per page (max 25 for Jikan)
            fetch_special_fields (bool): Whether to fetch special fields
            special_fields_to_fetch (list): List of specific special fields to fetch
            
        Returns:
            list: List of anime data dictionaries
        """
        # Available special fields in Jikan
        all_special_fields = ['recommendations', 'statistics']
        
        # Determine which special fields to fetch
        if special_fields_to_fetch is None and fetch_special_fields:
            special_fields_to_fetch = all_special_fields.copy()
        elif not fetch_special_fields:
            special_fields_to_fetch = []
        else:
            # Validate the requested fields
            special_fields_to_fetch = [f for f in special_fields_to_fetch if f in all_special_fields]
        
        all_anime = []
        page = 1
        remaining = limit
        
        print(f"Retrieving up to {limit} anime titles using Jikan API...")
        
        while remaining > 0:
            # Jikan v4 limits to max 25 per page
            batch_size = min(page_size, remaining, 25)
            
            url = f"{self.base_url}/top/anime"
            params = {
                'page': page,
                'limit': batch_size
            }
            
            # Handle Jikan rate limits
            self._handle_rate_limit()
            
            try:
                response = requests.get(url, params=params)
                response.raise_for_status()
                data = response.json()
                
                # Extract anime data from response
                batch_anime = data.get('data', [])
                
                if not batch_anime:
                    break  # No more results
                    
                all_anime.extend(batch_anime)
                
                # Update progress
                retrieved = len(batch_anime)
                remaining -= retrieved
                page += 1
                
                # Break if we've reached pagination limit or total limit
                if page > data.get('pagination', {}).get('last_visible_page', 1):
                    break
                
            except requests.RequestException as e:
                print(f"Error retrieving anime data from Jikan: {e}")
                # Jikan sometimes needs a longer wait on error
                time.sleep(10)
                continue
        
        if not special_fields_to_fetch:
            print(f"Successfully retrieved {len(all_anime)} anime titles from Jikan API (basic data only).")
            return all_anime
        
        print(f"Successfully retrieved {len(all_anime)} anime titles from Jikan API.")
        print(f"Now fetching additional fields: {', '.join(special_fields_to_fetch)}")
        
        # Now that we have the basic data, fetch recommendations and stats for each anime
        enriched_anime = []
        
        for anime in tqdm(all_anime, desc="Fetching detailed anime data from Jikan"):
            anime_id = anime['mal_id']
            
            # Get recommendations if requested
            if 'recommendations' in special_fields_to_fetch:
                try:
                    # Handle Jikan rate limits
                    self._handle_rate_limit()
                    
                    rec_url = f"{self.base_url}/anime/{anime_id}/recommendations"
                    rec_response = requests.get(rec_url)
                    
                    if rec_response.status_code == 200:
                        rec_data = rec_response.json()
                        anime['recommendations'] = rec_data.get('data', [])
                except:
                    # Don't let recommendation failure stop the process
                    anime['recommendations'] = []
            
            # Get statistics if requested
            if 'statistics' in special_fields_to_fetch:
                try:
                    # Handle Jikan rate limits
                    self._handle_rate_limit()
                    
                    stats_url = f"{self.base_url}/anime/{anime_id}/statistics"
                    stats_response = requests.get(stats_url)
                    
                    if stats_response.status_code == 200:
                        stats_data = stats_response.json()
                        anime['statistics'] = stats_data.get('data', {})
                except:
                    # Don't let statistics failure stop the process
                    anime['statistics'] = {}
            
            enriched_anime.append(anime)
        
        return enriched_anime
    
    def get_user_anime_list(self, username, limit=1000):
        """
        Get a user's anime list including their ratings from Jikan API.
        
        Args:
            username (str): MyAnimeList username
            limit (int): Maximum number of anime to retrieve from user's list
            
        Returns:
            list: User's anime list data
        """
        all_user_anime = []
        page = 1
        remaining = limit
        
        # Different status values for Jikan
        statuses = ['completed', 'watching', 'on_hold', 'dropped', 'plan_to_watch']
        
        print(f"Retrieving anime list for user '{username}' using Jikan API...")
        
        for status in statuses:
            page = 1
            local_remaining = min(200, remaining)  # Limit per status
            
            while local_remaining > 0:
                # Handle Jikan rate limits
                self._handle_rate_limit()
                
                url = f"{self.base_url}/users/{username}/animelist"
                params = {
                    'page': page,
                    'status': status,
                    'limit': 25  # Jikan v4 page size
                }
                
                try:
                    response = requests.get(url, params=params)
                    response.raise_for_status()
                    data = response.json()
                    
                    batch_data = data.get('data', [])
                    if not batch_data:
                        break  # No more results for this status
                        
                    # Process each entry
                    for item in batch_data:
                        user_entry = {
                            'username': username,
                            'anime_id': item['anime']['mal_id'],
                            'status': status,
                            'score': item.get('score', 0),
                            'watched_episodes': item.get('episodes_watched', 0),
                            'start_date': item.get('start_date'),
                            'end_date': item.get('end_date'),
                            'comments': item.get('comments', '')
                        }
                        all_user_anime.append(user_entry)
                    
                    # Update tracking
                    retrieved = len(batch_data)
                    local_remaining -= retrieved
                    remaining -= retrieved
                    page += 1
                    
                    # Break if we've reached pagination limit
                    if page > data.get('pagination', {}).get('last_visible_page', 1):
                        break
                        
                except requests.RequestException as e:
                    print(f"Error retrieving user anime list from Jikan: {e}")
                    time.sleep(10)  # Longer wait on error
                    break  # Move to next status on error
        
        print(f"Retrieved {len(all_user_anime)} anime entries for user '{username}' from Jikan")
        return all_user_anime
    
    def get_multiple_users(self, usernames, limit_per_user=1000):
        """
        Get anime lists for multiple users from Jikan API.
        
        Args:
            usernames (list): List of MyAnimeList usernames
            limit_per_user (int): Maximum number of anime to retrieve per user
            
        Returns:
            dict: Dictionary with username keys and user anime list values
        """
        all_user_data = {}
        
        for username in tqdm(usernames, desc="Retrieving user data"):
            user_anime = self.get_user_anime_list(username, limit=limit_per_user)
            all_user_data[username] = user_anime
            # More aggressive rate limiting between users
            time.sleep(2)
            
        print(f"Successfully retrieved data for {len(usernames)} users")
        return all_user_data


class AnimeDataManager:
    """
    A utility class to manage anime data extraction using either MAL or Jikan APIs.
    This class provides a unified interface to both extractors and handles the API choice.
    """
    
    def __init__(self, client_id=None):
        """
        Initialize the data manager with optional MAL client ID.
        
        Args:
            client_id (str, optional): MAL API client ID. If provided, MAL API will be used
                                      when possible; otherwise Jikan will be used.
        """
        self.mal_extractor = None
        self.jikan_extractor = JikanExtractor()
        
        if client_id:
            self.mal_extractor = MALExtractor(client_id)
    
    def get_anime_recommendations(self, anime_ids, use_mal=True):
        """
        Get recommendations for a list of anime IDs.
        
        Args:
            anime_ids (list): List of anime IDs to get recommendations for
            use_mal (bool): Whether to prefer MAL API (if available) over Jikan
            
        Returns:
            dict: Dictionary mapping anime IDs to their recommendations
        """
        if use_mal and self.mal_extractor:
            return self.mal_extractor.get_anime_recommendations(anime_ids)
        else:
            return self.jikan_extractor.get_anime_recommendations(anime_ids)
    
    def get_anime_list(self, limit=500, use_mal=True, fetch_special_fields=True, special_fields_to_fetch=None):
        """
        Get a list of anime with ratings.
        
        Args:
            limit (int): Maximum number of anime to retrieve
            use_mal (bool): Whether to prefer MAL API (if available) over Jikan
            fetch_special_fields (bool): Whether to fetch special fields
            special_fields_to_fetch (list): List of specific special fields to fetch
            
        Returns:
            list: List of anime data dictionaries
        """
        if use_mal and self.mal_extractor:
            return self.mal_extractor.get_anime_list(
                limit=limit, 
                fetch_special_fields=fetch_special_fields,
                special_fields_to_fetch=special_fields_to_fetch
            )
        else:
            return self.jikan_extractor.get_anime_list(
                limit=limit,
                fetch_special_fields=fetch_special_fields,
                special_fields_to_fetch=special_fields_to_fetch
            )
    
    def get_user_anime_list(self, username, limit=1000, use_mal=True):
        """
        Get a user's anime list including their ratings.
        
        Args:
            username (str): MyAnimeList username
            limit (int): Maximum number of anime to retrieve from user's list
            use_mal (bool): Whether to prefer MAL API (if available) over Jikan
            
        Returns:
            list: User's anime list data
        """
        if use_mal and self.mal_extractor:
            return self.mal_extractor.get_user_anime_list(username, limit)
        else:
            return self.jikan_extractor.get_user_anime_list(username, limit)
    
    def get_multiple_users(self, usernames, limit_per_user=1000, use_mal=True):
        """
        Get anime lists for multiple users.
        
        Args:
            usernames (list): List of MyAnimeList usernames
            limit_per_user (int): Maximum number of anime to retrieve per user
            use_mal (bool): Whether to prefer MAL API (if available) over Jikan
            
        Returns:
            dict: Dictionary with username keys and user anime list values
        """
        if use_mal and self.mal_extractor:
            return self.mal_extractor.get_multiple_users(usernames, limit_per_user)
        else:
            return self.jikan_extractor.get_multiple_users(usernames, limit_per_user)
    
    def save_data_to_json(self, data, filepath):
        """
        Save data to a JSON file.
        
        Args:
            data: Data to save (list or dict)
            filepath (str): Path to save the JSON file
            
        Returns:
            str: Path to the saved file
        """
        # We can use either extractor's method since it's the same
        return self.jikan_extractor.save_data_to_json(data, filepath)


# Example usage
if __name__ == "__main__":
    # Example with client ID (using MAL API when possible)
    CLIENT_ID = "your_client_id_here"  # Replace with your actual client ID
    anime_manager = AnimeDataManager(CLIENT_ID)
    
    # Example 1: Get anime recommendations using preferred API
    anime_ids = [5114, 9253, 28851, 1535, 30276]  # Example IDs
    recommendations = anime_manager.get_anime_recommendations(anime_ids, use_mal=True)
    anime_manager.save_data_to_json(recommendations, "anime_data/recommendations.json")
    
    # Example 2: Get anime list using Jikan API
    jikan_anime_list = anime_manager.get_anime_list(
        limit=100, 
        use_mal=False,  # Force using Jikan
        fetch_special_fields=True,
        special_fields_to_fetch=['recommendations']
    )
    anime_manager.save_data_to_json(jikan_anime_list, "anime_data/jikan_anime_list.json")
    
    # Example 3: Create a Jikan-only extractor
    jikan_only = AnimeDataManager()  # No client ID = Jikan only
    user_anime = jikan_only.get_user_anime_list("username", limit=500)
    jikan_only.save_data_to_json(user_anime, "anime_data/user_anime_list.json")