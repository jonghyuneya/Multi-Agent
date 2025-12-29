"""
Data loader for the Korean closing market briefing pipeline.

Provides extensible loading of source data from various formats and locations,
reusing patterns from the existing "brief AI" (econ_briefing) pipeline.

Supports:
- TradingEconomics scraper output (CSV files)
- Processed JSON from econ_briefing pipeline
- Local directory structure
- (Future) AWS S3 storage
"""

import csv
import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class ClosingBriefingDataLoader:
    """
    Extensible data loader for closing briefing source data.
    
    Integrates with existing econ_briefing pipeline data sources:
    - te_scraper_output/calendar/*.csv - Economic calendar events
    - te_scraper_output/indicators/*.csv - Macro indicators
    - te_scraper_output/fomc_press_conferences/*.pdf - FOMC transcripts
    - processed/*.json - Processed data from econ_briefing pipeline
    - AWS DynamoDB - Economic news articles
    """
    
    def __init__(
        self,
        source_path: str,
        load_news_from_dynamodb: bool = True,
        dynamodb_table: str = "kubig-YahoofinanceNews",
        dynamodb_region: str = "ap-northeast-2",
        dynamodb_profile: str = "jonghyun",
    ):
        """
        Initialize the data loader.
        
        Args:
            source_path: Path to source data directory (e.g., econ_briefing/data)
            load_news_from_dynamodb: Whether to load news from AWS DynamoDB
            dynamodb_table: DynamoDB table name for news
            dynamodb_region: AWS region for DynamoDB
            dynamodb_profile: AWS SSO profile name
        """
        self.source_path = Path(source_path)
        self._data_cache: Dict[str, Any] = {}
        
        # DynamoDB configuration
        self.load_news_from_dynamodb = load_news_from_dynamodb
        self.dynamodb_table = dynamodb_table
        self.dynamodb_region = dynamodb_region
        self.dynamodb_profile = dynamodb_profile
    
    def load_all_sources(self) -> Dict[str, Any]:
        """
        Load all available source data from the existing pipeline structure.
        
        Returns:
            Dictionary containing all loaded source data:
            - macro_data: Macroeconomic indicators (from indicators CSV or processed JSON)
            - calendar_events: Economic calendar events (from calendar CSV or processed JSON)
            - fomc_events: FOMC-related events (from processed JSON)
            - news_data: News headlines and summaries
            - earnings_data: Company earnings results
            - market_summary: Market indices and sector performance
        """
        logger.info(f"Loading source data from: {self.source_path}")
        
        sources: Dict[str, Any] = self._get_empty_sources()
        
        # First, check if source_path IS the te_calendar_scraper output directory
        # (has calendar, indicators, fomc_press_conferences subdirectories)
        calendar_dir = self.source_path / "calendar"
        indicators_dir = self.source_path / "indicators"
        fomc_dir = self.source_path / "fomc_press_conferences"
        
        if calendar_dir.exists() or indicators_dir.exists() or fomc_dir.exists():
            logger.info("Found te_calendar_scraper output structure, loading CSV data...")
            sources.update(self._load_from_te_scraper(self.source_path))
        
        # Also try loading from te_scraper_output subdirectory (legacy structure)
        te_scraper_dir = self.source_path / "te_scraper_output"
        if te_scraper_dir.exists():
            logger.info("Found te_scraper_output directory, loading CSV data...")
            loaded = self._load_from_te_scraper(te_scraper_dir)
            # Merge, don't overwrite if already loaded
            for key, value in loaded.items():
                if not sources.get(key):
                    sources[key] = value
        
        # Try loading from processed JSON (from econ_briefing pipeline)
        processed_dir = self.source_path / "processed"
        if processed_dir.exists():
            logger.info("Found processed directory, loading JSON data...")
            processed_data = self._load_from_processed_json(processed_dir)
            # Merge with existing data (don't overwrite if already loaded)
            for key, value in processed_data.items():
                if not sources.get(key):
                    sources[key] = value
        
        # Try loading news from DynamoDB (AWS)
        if self.load_news_from_dynamodb and not sources.get('news_data'):
            logger.info("Attempting to load news from AWS DynamoDB...")
            sources['news_data'] = self._load_news_from_dynamodb()
        
        # Fallback: Try loading from economic_news directory
        news_dir = self.source_path / "economic_news"
        if news_dir.exists() and not sources.get('news_data'):
            logger.info("Found economic_news directory, loading cached news...")
            sources['news_data'] = self._load_news_from_directory(news_dir)
        
        # If source_path is a single JSON bundle file
        if self.source_path.is_file() and self.source_path.suffix == '.json':
            sources = self._load_from_json_bundle()
        
        # Also check for direct JSON files in source_path
        if self.source_path.is_dir():
            direct_data = self._load_direct_json_files()
            for key, value in direct_data.items():
                if not sources.get(key):
                    sources[key] = value
        
        self._data_cache = sources
        
        # Log what was loaded
        for key, value in sources.items():
            if isinstance(value, list):
                logger.info(f"  {key}: {len(value)} items")
            elif isinstance(value, dict):
                logger.info(f"  {key}: {len(value)} keys")
        
        return sources
    
    def _load_from_te_scraper(self, te_scraper_dir: Path) -> Dict[str, Any]:
        """Load data from TradingEconomics scraper output (CSV files)."""
        data: Dict[str, Any] = {}
        
        # Load calendar events from CSV
        calendar_dir = te_scraper_dir / "calendar"
        if calendar_dir.exists():
            data['calendar_events'] = self._load_calendar_csv(calendar_dir)
        
        # Load macro indicators from CSV
        indicators_dir = te_scraper_dir / "indicators"
        if indicators_dir.exists():
            data['macro_data'] = self._load_indicators_csv(indicators_dir)
        
        # Load FOMC events from PDF filenames (metadata only)
        fomc_dir = te_scraper_dir / "fomc_press_conferences"
        if fomc_dir.exists():
            data['fomc_events'] = self._load_fomc_metadata(fomc_dir)
        
        return data
    
    def _load_calendar_csv(self, calendar_dir: Path) -> List[Dict]:
        """Load calendar events from the most recent CSV file."""
        csv_files = sorted(calendar_dir.glob("calendar_US_*.csv"))
        if not csv_files:
            logger.warning("No calendar CSV files found")
            return []
        
        # Use the most recent file
        csv_path = csv_files[-1]
        logger.info(f"Loading calendar from: {csv_path.name}")
        
        events = []
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                event = {
                    "id": f"cal_{row.get('datetime_utc', '').replace(':', '').replace('-', '')}_{row.get('title', '').replace(' ', '_')[:30]}",
                    "date": row.get('datetime_utc', '').split('T')[0] if row.get('datetime_utc') else '',
                    "time": row.get('raw_time_text', ''),
                    "name": row.get('title', ''),
                    "importance": self._map_impact_to_importance(row.get('impact', '2')),
                    "description": f"{row.get('category', '')} event for {row.get('country', 'United States')}",
                    "category": row.get('category', ''),
                    "meta": {
                        "datetime_utc": row.get('datetime_utc', ''),
                        "datetime_kst": row.get('datetime_kst', ''),
                        "impact": row.get('impact', ''),
                        "country": row.get('country', ''),
                        "source_url": row.get('source_url', '')
                    }
                }
                events.append(event)
        
        logger.info(f"Loaded {len(events)} calendar events")
        return events
    
    def _load_indicators_csv(self, indicators_dir: Path) -> List[Dict]:
        """Load macro indicators from the most recent CSV file."""
        csv_files = sorted(indicators_dir.glob("indicators_US_*.csv"))
        if not csv_files:
            logger.warning("No indicators CSV files found")
            return []
        
        # Use the most recent file
        csv_path = csv_files[-1]
        logger.info(f"Loading indicators from: {csv_path.name}")
        
        indicators = []
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    value = float(row.get('latest_value', 0))
                except (ValueError, TypeError):
                    value = 0.0
                
                indicator = {
                    "name": row.get('indicator_name', ''),
                    "unit": row.get('unit', ''),
                    "values": [value],
                    "dates": [row.get('obs_date', '')],
                    "value": value,  # Convenience field
                    "date": row.get('obs_date', ''),
                    "meta": {
                        "bucket": row.get('indicator_bucket', ''),
                        "source_url": row.get('source_url', ''),
                        "raw_source_note": row.get('raw_source_note', ''),
                        "day_change": row.get('day_change', ''),
                        "month_change": row.get('month_change', ''),
                        "year_change": row.get('year_change', '')
                    }
                }
                indicators.append(indicator)
        
        logger.info(f"Loaded {len(indicators)} macro indicators")
        return indicators
    
    def _load_fomc_metadata(self, fomc_dir: Path) -> List[Dict]:
        """Load FOMC event metadata from PDF filenames."""
        events = []
        pdf_files = sorted(fomc_dir.glob("*.pdf"))
        
        month_map = {
            'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04',
            'may': '05', 'jun': '06', 'jul': '07', 'aug': '08',
            'sep': '09', 'oct': '10', 'nov': '11', 'dec': '12'
        }
        
        for pdf_file in pdf_files:
            filename = pdf_file.stem
            parts = filename.split('_')
            
            if len(parts) >= 3:
                year = parts[0]
                month = parts[1]
                dates = parts[2]
                
                month_num = month_map.get(month.lower(), '01')
                first_date = dates.split('-')[0] if '-' in dates else dates
                date_str = f"{year}-{month_num}-{first_date.zfill(2)}"
                
                event = {
                    "id": f"fomc_{filename}",
                    "date": date_str,
                    "title": f"FOMC Press Conference - {month.capitalize()} {year}",
                    "type": "press_conference",
                    "text_snippet": f"FOMC 회의 기자회견 ({dates} {month.capitalize()} {year})",
                    "full_text": None,
                    "meta": {
                        "meeting_dates": f"{year}-{month_num}-{dates}",
                        "pdf_path": str(pdf_file),
                        "filename": pdf_file.name
                    }
                }
                events.append(event)
        
        logger.info(f"Loaded {len(events)} FOMC events")
        return events
    
    def _load_from_processed_json(self, processed_dir: Path) -> Dict[str, Any]:
        """Load data from processed JSON files (econ_briefing pipeline output)."""
        data: Dict[str, Any] = {}
        
        # Map of JSON files to data keys
        file_mapping = {
            'macro_data.json': 'macro_data',
            'calendar_events.json': 'calendar_events',
            'fomc_events.json': 'fomc_events',
        }
        
        for filename, key in file_mapping.items():
            file_path = processed_dir / filename
            if file_path.exists():
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data[key] = json.load(f)
                    logger.debug(f"Loaded {filename}")
                except Exception as e:
                    logger.warning(f"Error loading {filename}: {e}")
        
        return data
    
    def _load_direct_json_files(self) -> Dict[str, Any]:
        """Load JSON files directly from source_path directory."""
        data: Dict[str, Any] = {}
        
        file_mapping = {
            'macro_data.json': 'macro_data',
            'earnings_data.json': 'earnings_data',
            'news_data.json': 'news_data',
            'calendar_events.json': 'calendar_events',
            'fomc_events.json': 'fomc_events',
            'market_summary.json': 'market_summary',
        }
        
        for filename, key in file_mapping.items():
            file_path = self.source_path / filename
            if file_path.exists():
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data[key] = json.load(f)
                    logger.debug(f"Loaded {filename}")
                except Exception as e:
                    logger.warning(f"Error loading {filename}: {e}")
        
        return data
    
    def _load_from_json_bundle(self) -> Dict[str, Any]:
        """Load all data from a single JSON bundle file."""
        try:
            with open(self.source_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            return {
                'macro_data': data.get('macro_data', []),
                'earnings_data': data.get('earnings_data', []),
                'news_data': data.get('news_data', []),
                'calendar_events': data.get('calendar_events', []),
                'fomc_events': data.get('fomc_events', []),
                'market_summary': data.get('market_summary', {}),
            }
        except Exception as e:
            logger.error(f"Error loading JSON bundle: {e}")
            return self._get_empty_sources()
    
    def _load_news_from_dynamodb(self) -> List[Dict]:
        """Load news from AWS DynamoDB using econ_briefing loader."""
        try:
            import boto3
            from boto3.dynamodb.conditions import Attr
            from datetime import datetime, timedelta
            from decimal import Decimal
            
            # Initialize boto3 session with SSO profile
            logger.info(f"Connecting to DynamoDB with profile: {self.dynamodb_profile}")
            session = boto3.Session(profile_name=self.dynamodb_profile)
            dynamodb = session.resource('dynamodb', region_name=self.dynamodb_region)
            table = dynamodb.Table(self.dynamodb_table)
            
            # Test connection
            table.table_status
            logger.info(f"Connected to DynamoDB table: {self.dynamodb_table}")
            
            # Calculate cutoff date (7 days back)
            cutoff_date = datetime.now() - timedelta(days=7)
            cutoff_timestamp = cutoff_date.strftime('%Y-%m-%d')
            
            # Scan with date filter - use 'publish_et_iso' field from kubig-YahoofinanceNews table
            # The field format is like '2025-11-18T11:01:28-05:00'
            filter_expression = Attr('publish_et_iso').gte(cutoff_timestamp)
            response = table.scan(FilterExpression=filter_expression, Limit=50)
            items = response.get('Items', [])
            
            # Handle pagination (limit to 100 items total)
            while 'LastEvaluatedKey' in response and len(items) < 100:
                response = table.scan(
                    FilterExpression=filter_expression,
                    ExclusiveStartKey=response['LastEvaluatedKey'],
                    Limit=50
                )
                items.extend(response.get('Items', []))
            
            logger.info(f"Retrieved {len(items)} items from DynamoDB")
            
            # Convert to our news format (map kubig-YahoofinanceNews schema to our format)
            news_items = []
            for item in items:
                # Convert Decimal to float
                def convert_decimals(obj):
                    if isinstance(obj, Decimal):
                        return float(obj)
                    elif isinstance(obj, dict):
                        return {k: convert_decimals(v) for k, v in obj.items()}
                    elif isinstance(obj, list):
                        return [convert_decimals(i) for i in obj]
                    return obj
                
                item = convert_decimals(item)
                
                # Map kubig-YahoofinanceNews schema to our format:
                # kubig schema: pk, path, publish_et_iso, et_iso, provider, url, title, tickers, related_articles
                news_item = {
                    "headline": item.get('title', ''),
                    "source": item.get('provider', 'Yahoo Finance'),
                    "category": self._categorize_news_by_tickers(item.get('tickers', [])),
                    "summary": item.get('title', ''),  # Use title as summary since no separate summary field
                    "market_impact": "",
                    "tags": item.get('tickers', []),
                    "published_date": item.get('publish_et_iso', ''),
                    "relevance_score": 0.7,  # Default relevance
                    "url": item.get('url', ''),
                    "tickers": item.get('tickers', []),
                }
                if news_item["headline"]:  # Only add if there's a title
                    news_items.append(news_item)
            
            # Sort by relevance and date
            news_items.sort(
                key=lambda x: (x.get('relevance_score', 0.5), x.get('published_date', '')),
                reverse=True
            )
            
            # Limit to top 30
            news_items = news_items[:30]
            
            logger.info(f"Loaded {len(news_items)} news articles from DynamoDB")
            return news_items
            
        except ImportError:
            logger.warning("boto3 not available for DynamoDB access")
            return []
        except Exception as e:
            logger.warning(f"Could not load news from DynamoDB: {e}")
            logger.warning("Make sure to run: aws sso login --profile %s", self.dynamodb_profile)
            return []
    
    def _categorize_news(self, tags: List[str]) -> str:
        """Categorize news based on tags."""
        tags_lower = [t.lower() for t in tags]
        
        if any(t in tags_lower for t in ['fed', 'fomc', 'interest rate', 'inflation', 'cpi', 'ppi', 'gdp']):
            return 'macro'
        elif any(t in tags_lower for t in ['china', 'europe', 'geopolitical', 'trade war', 'tariff']):
            return 'geopolitical'
        elif any(t in tags_lower for t in ['earnings', 'revenue', 'eps', 'guidance']):
            return 'company'
        else:
            return 'sector'
    
    def _categorize_news_by_tickers(self, tickers: List[str]) -> str:
        """Categorize news based on stock tickers."""
        if not tickers:
            return 'sector'
        
        # Major tech tickers
        tech_tickers = ['AAPL', 'GOOGL', 'GOOG', 'MSFT', 'META', 'AMZN', 'NVDA', 'TSLA', 'AMD', 'INTC']
        # Financial tickers
        fin_tickers = ['JPM', 'BAC', 'GS', 'MS', 'C', 'WFC']
        # Energy tickers
        energy_tickers = ['XOM', 'CVX', 'COP', 'OXY', 'SLB']
        
        for ticker in tickers:
            ticker_upper = ticker.upper()
            if ticker_upper in tech_tickers:
                return 'company'
            elif ticker_upper in fin_tickers:
                return 'sector'
            elif ticker_upper in energy_tickers:
                return 'sector'
        
        return 'company'
    
    def _load_news_from_directory(self, news_dir: Path) -> List[Dict]:
        """Load news data from a directory of JSON files."""
        news_items = []
        for json_file in news_dir.glob('*.json'):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if isinstance(data, list):
                    news_items.extend(data)
                elif isinstance(data, dict):
                    news_items.append(data)
            except Exception as e:
                logger.warning(f"Error loading news file {json_file}: {e}")
        return news_items
    
    @staticmethod
    def _map_impact_to_importance(impact: str) -> str:
        """Map numeric impact to importance level."""
        try:
            impact_num = int(impact)
            if impact_num >= 3:
                return "high"
            elif impact_num == 2:
                return "medium"
            else:
                return "low"
        except (ValueError, TypeError):
            return "medium"
    
    @staticmethod
    def _get_empty_sources() -> Dict[str, Any]:
        """Return empty source structure."""
        return {
            'macro_data': [],
            'earnings_data': [],
            'news_data': [],
            'calendar_events': [],
            'fomc_events': [],
            'market_summary': {},
        }
    
    def get_cached_data(self) -> Dict[str, Any]:
        """Get previously loaded data from cache."""
        return self._data_cache


class EconBriefingDataLoader:
    """
    Wrapper to use the existing econ_briefing.data_loader.TEScraperDataLoader.
    
    This provides compatibility with the existing pipeline while adding
    closing briefing-specific functionality.
    """
    
    def __init__(self, data_dir: str = "econ_briefing/data/te_scraper_output"):
        """
        Initialize using the existing TEScraperDataLoader.
        
        Args:
            data_dir: Path to te_scraper output directory
        """
        self.data_dir = Path(data_dir)
        self._te_loader = None
    
    def _get_te_loader(self):
        """Get or create the TEScraperDataLoader."""
        if self._te_loader is None:
            try:
                from econ_briefing.data_loader import TEScraperDataLoader
                self._te_loader = TEScraperDataLoader(str(self.data_dir))
            except ImportError:
                logger.warning("Could not import TEScraperDataLoader, using fallback")
                return None
        return self._te_loader
    
    def load_all_sources(self) -> Dict[str, Any]:
        """Load all sources using the existing TEScraperDataLoader."""
        te_loader = self._get_te_loader()
        
        if te_loader:
            return te_loader.load_all_data()
        else:
            # Fallback to our own loader
            loader = ClosingBriefingDataLoader(str(self.data_dir.parent))
            return loader.load_all_sources()


class DynamoDBNewsLoader:
    """
    AWS DynamoDB news loader for closing briefing.
    
    Wraps the existing econ_briefing.dynamodb_news_loader to load
    economic news from AWS DynamoDB.
    """
    
    def __init__(
        self,
        table_name: str = "kubig-YahoofinanceNews",
        region_name: str = "ap-northeast-2",
        profile_name: str = "jonghyun",
    ):
        """
        Initialize DynamoDB news loader.
        
        Args:
            table_name: DynamoDB table name (default: kubig-YahoofinanceNews)
            region_name: AWS region
            profile_name: AWS SSO profile name
        """
        self.table_name = table_name
        self.region_name = region_name
        self.profile_name = profile_name
        self._loader = None
    
    def _get_loader(self):
        """Get or create the DynamoDB loader from econ_briefing."""
        if self._loader is None:
            try:
                # Try to import from econ_briefing
                from econ_briefing.dynamodb_news_loader import DynamoDBNewsLoader as DBLoader
                self._loader = DBLoader(
                    table_name=self.table_name,
                    region_name=self.region_name,
                    profile_name=self.profile_name,
                )
                logger.info(f"Connected to DynamoDB table: {self.table_name}")
            except ImportError as e:
                logger.warning(f"Could not import DynamoDBNewsLoader from econ_briefing: {e}")
                return None
            except Exception as e:
                logger.warning(f"Could not connect to DynamoDB: {e}")
                logger.warning("Make sure to run: aws sso login --profile %s", self.profile_name)
                return None
        return self._loader
    
    def load_news(
        self,
        days_back: int = 7,
        min_relevance: float = 0.0,
        limit: int = 20,
    ) -> List[Dict]:
        """
        Load news articles from DynamoDB.
        
        Args:
            days_back: Days to look back
            min_relevance: Minimum relevance score (0-1)
            limit: Maximum number of articles
            
        Returns:
            List of news article dictionaries
        """
        loader = self._get_loader()
        if loader is None:
            logger.warning("DynamoDB loader not available, returning empty list")
            return []
        
        try:
            articles = loader.load_news_articles(
                days_back=days_back,
                min_relevance=min_relevance,
                limit=limit,
            )
            logger.info(f"Loaded {len(articles)} news articles from DynamoDB")
            return articles
        except Exception as e:
            logger.error(f"Error loading news from DynamoDB: {e}")
            return []
    
    def create_news_summary(
        self,
        days_back: int = 7,
        max_articles: int = 10,
        min_relevance: float = 0.7,
    ) -> Dict:
        """
        Create a news summary for the briefing.
        
        Args:
            days_back: Days to look back
            max_articles: Maximum articles to include
            min_relevance: Minimum relevance score
            
        Returns:
            News summary dictionary
        """
        loader = self._get_loader()
        if loader is None:
            return {"articles": [], "total_articles": 0}
        
        try:
            return loader.create_news_summary_for_briefing(
                days_back=days_back,
                max_articles=max_articles,
                min_relevance=min_relevance,
            )
        except Exception as e:
            logger.error(f"Error creating news summary: {e}")
            return {"articles": [], "total_articles": 0}


class S3DataLoader:
    """
    AWS S3 data loader for closing briefing source data.
    
    Placeholder for future AWS integration.
    """
    
    def __init__(self, bucket: str, prefix: str = ''):
        """
        Initialize S3 data loader.
        
        Args:
            bucket: S3 bucket name
            prefix: Key prefix for source files
        """
        self.bucket = bucket
        self.prefix = prefix
        self._client = None
    
    def _get_client(self):
        """Get or create S3 client."""
        if self._client is None:
            try:
                import boto3
                self._client = boto3.client('s3')
            except ImportError:
                raise ImportError("boto3 is required for S3 data loading")
        return self._client
    
    def load_all_sources(self) -> Dict[str, Any]:
        """Load all source data from S3."""
        logger.info(f"Loading source data from S3: s3://{self.bucket}/{self.prefix}")
        raise NotImplementedError("S3 data loading not yet implemented")


def create_sample_source_data(output_path: str) -> None:
    """
    Create sample source data for testing the pipeline.
    
    Args:
        output_path: Directory to save sample data
    """
    output_dir = Path(output_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Sample macro data (matching te_scraper format)
    macro_data = [
        {
            "name": "CPI YoY",
            "unit": "percent",
            "values": [3.0],
            "dates": ["2025-12-01"],
            "value": 3.0,
            "date": "2025-12-01",
            "meta": {"bucket": "CPI", "source_url": "https://tradingeconomics.com/united-states/inflation-cpi"}
        },
        {
            "name": "Core CPI YoY",
            "unit": "percent",
            "values": [3.3],
            "dates": ["2025-12-01"],
            "value": 3.3,
            "date": "2025-12-01",
            "meta": {"bucket": "CPI", "source_url": "https://tradingeconomics.com/united-states/core-inflation-rate"}
        },
        {
            "name": "ISM Manufacturing PMI",
            "unit": "points",
            "values": [52.5],
            "dates": ["2025-12-01"],
            "value": 52.5,
            "date": "2025-12-01",
            "meta": {"bucket": "ISM", "source_url": "https://tradingeconomics.com/united-states/manufacturing-pmi"}
        },
        {
            "name": "ISM Services PMI",
            "unit": "points",
            "values": [54.8],
            "dates": ["2025-12-01"],
            "value": 54.8,
            "date": "2025-12-01",
            "meta": {"bucket": "ISM", "source_url": "https://tradingeconomics.com/united-states/services-pmi"}
        },
        {
            "name": "US 10Y Yield",
            "unit": "percent",
            "values": [4.08],
            "dates": ["2025-12-04"],
            "value": 4.08,
            "date": "2025-12-04",
            "meta": {"bucket": "UST", "source_url": "https://tradingeconomics.com/united-states/government-bond-yield"}
        },
        {
            "name": "US 2Y Yield",
            "unit": "percent",
            "values": [3.58],
            "dates": ["2025-12-04"],
            "value": 3.58,
            "date": "2025-12-04",
            "meta": {"bucket": "UST", "source_url": "https://tradingeconomics.com/united-states/government-bond-yield"}
        },
    ]
    
    # Sample earnings data
    earnings_data = [
        {
            "company_name": "NVIDIA",
            "ticker": "NVDA",
            "eps_actual": 5.16,
            "eps_estimate": 4.85,
            "revenue_actual": 35.1e9,
            "revenue_estimate": 33.0e9,
            "yoy_growth_pct": 94,
            "beat_or_miss": "beat",
            "sector": "Technology",
            "key_drivers": ["AI 데이터센터 수요 급증", "Hopper GPU 출하량 증가", "클라우드 서비스 업체 투자 확대"],
            "stock_reaction": "+8% 상승"
        },
        {
            "company_name": "Salesforce",
            "ticker": "CRM",
            "eps_actual": 2.41,
            "eps_estimate": 2.35,
            "revenue_actual": 9.44e9,
            "revenue_estimate": 9.35e9,
            "yoy_growth_pct": 11,
            "beat_or_miss": "beat",
            "sector": "Technology",
            "key_drivers": ["AI 기반 CRM 솔루션 성장", "구독 매출 안정", "기업 디지털 전환 수요"],
            "stock_reaction": "+5% 상승"
        },
        {
            "company_name": "Dollar General",
            "ticker": "DG",
            "eps_actual": 1.70,
            "eps_estimate": 1.95,
            "revenue_actual": 10.2e9,
            "revenue_estimate": 10.5e9,
            "yoy_growth_pct": -3,
            "beat_or_miss": "miss",
            "sector": "Consumer Discretionary",
            "key_drivers": ["소비자 지출 둔화", "가격 저항 심화", "저소득층 소비 위축"],
            "stock_reaction": "-12% 하락"
        },
        {
            "company_name": "Broadcom",
            "ticker": "AVGO",
            "eps_actual": 12.15,
            "eps_estimate": 11.80,
            "revenue_actual": 14.1e9,
            "revenue_estimate": 13.8e9,
            "yoy_growth_pct": 51,
            "beat_or_miss": "beat",
            "sector": "Technology",
            "key_drivers": ["AI 네트워킹 칩 수요", "VMware 인수 시너지", "데이터센터 인프라 투자"],
            "stock_reaction": "+4% 상승"
        },
    ]
    
    # Sample news data
    news_data = [
        {
            "headline": "Fed 파월 의장, 금리 인하 서두르지 않겠다 발언",
            "source": "Reuters",
            "category": "macro",
            "summary": "파월 의장은 인플레이션이 2% 목표에 도달하기까지 시간이 걸릴 것이라며 금리 인하에 신중한 입장을 재확인했습니다. '경제가 강하기 때문에 서두를 필요가 없다'고 강조했습니다.",
            "market_impact": "국채 금리 상승, 달러 강세, 주식시장 혼조",
            "tags": ["Fed", "금리", "인플레이션", "파월"]
        },
        {
            "headline": "엔비디아, AI 칩 수요로 사상 최대 실적 달성",
            "source": "Bloomberg",
            "category": "company",
            "summary": "엔비디아가 AI 데이터센터 투자 붐에 힘입어 분기 매출 350억 달러를 돌파하며 시장 기대를 크게 상회했습니다. CEO 젠슨 황은 '새로운 산업혁명이 시작됐다'고 언급했습니다.",
            "market_impact": "기술주 강세, 반도체 섹터 상승, 나스닥 신고가",
            "tags": ["NVIDIA", "AI", "반도체", "실적"]
        },
        {
            "headline": "미국 11월 고용지표 예상 상회, 노동시장 여전히 견조",
            "source": "WSJ",
            "category": "macro",
            "summary": "11월 비농업 고용은 22만 7천 명 증가하며 예상치 20만 명을 상회했습니다. 실업률은 4.2%로 안정적인 수준을 유지했습니다.",
            "market_impact": "금리 인하 기대 후퇴, 달러 강세",
            "tags": ["고용", "노동시장", "NFP"]
        },
        {
            "headline": "중국 부동산 위기 심화, 헝다그룹 청산 절차 시작",
            "source": "FT",
            "category": "geopolitical",
            "summary": "중국 헝다그룹의 청산 절차가 시작되면서 글로벌 투자심리에 부담으로 작용하고 있습니다. 중국 부동산 섹터 불안이 지속되고 있습니다.",
            "market_impact": "아시아 시장 약세, 위험자산 회피, 원자재 하락",
            "tags": ["중국", "부동산", "헝다", "리스크"]
        },
    ]
    
    # Sample calendar events (matching te_scraper format)
    calendar_events = [
        {
            "id": "cal_20251205_NFP",
            "date": "2025-12-05",
            "time": "08:30 AM",
            "name": "Non Farm Payrolls",
            "importance": "high",
            "description": "미국 비농업 고용지표 - 노동시장 건전성의 핵심 지표",
            "category": "Employment",
            "meta": {"impact": "3", "country": "United States"}
        },
        {
            "id": "cal_20251210_CPI",
            "date": "2025-12-10",
            "time": "08:30 AM",
            "name": "CPI YoY",
            "importance": "high",
            "description": "미국 소비자물가지수 - 연준 정책 결정의 핵심 데이터",
            "category": "Inflation",
            "meta": {"impact": "3", "country": "United States"}
        },
        {
            "id": "cal_20251211_FOMC",
            "date": "2025-12-11",
            "time": "02:00 PM",
            "name": "FOMC Interest Rate Decision",
            "importance": "high",
            "description": "연준 금리 결정 및 점도표 발표",
            "category": "Interest Rate",
            "meta": {"impact": "3", "country": "United States"}
        },
        {
            "id": "cal_20251212_ECB",
            "date": "2025-12-12",
            "time": "07:45 AM",
            "name": "ECB Interest Rate Decision",
            "importance": "high",
            "description": "유럽중앙은행 금리 결정",
            "category": "Interest Rate",
            "meta": {"impact": "3", "country": "Euro Area"}
        },
        {
            "id": "cal_20251213_RetailSales",
            "date": "2025-12-13",
            "time": "08:30 AM",
            "name": "Retail Sales MoM",
            "importance": "medium",
            "description": "미국 소매판매 - 소비 동향 파악",
            "category": "Retail",
            "meta": {"impact": "2", "country": "United States"}
        },
    ]
    
    # Sample FOMC events
    fomc_events = [
        {
            "id": "fomc_2024_dec_17-18",
            "date": "2024-12-18",
            "title": "FOMC Press Conference - Dec 2024",
            "type": "press_conference",
            "text_snippet": "12월 FOMC 회의에서 연준은 금리를 25bp 인하했습니다. 파월 의장은 2025년 금리 인하 속도가 둔화될 것임을 시사했습니다.",
            "full_text": None,
            "meta": {"meeting_dates": "2024-12-17-18"}
        },
        {
            "id": "fomc_2025_jan_28-29",
            "date": "2025-01-29",
            "title": "FOMC Press Conference - Jan 2025",
            "type": "press_conference",
            "text_snippet": "1월 FOMC 회의에서 연준은 금리를 동결했습니다. 인플레이션 진전 상황을 더 지켜볼 필요가 있다고 언급했습니다.",
            "full_text": None,
            "meta": {"meeting_dates": "2025-01-28-29"}
        },
    ]
    
    # Sample market summary
    market_summary = {
        "date": "2025-12-04",
        "indices": {
            "S&P 500": {"close": 6050.23, "change_pct": 0.85, "change_pts": 51.2},
            "NASDAQ": {"close": 19450.67, "change_pct": 1.23, "change_pts": 236.5},
            "DOW": {"close": 44250.12, "change_pct": 0.42, "change_pts": 185.3},
            "Russell 2000": {"close": 2380.45, "change_pct": 0.65, "change_pts": 15.4},
        },
        "sectors": {
            "Technology": {"change_pct": 1.5, "leaders": ["NVDA", "CRM", "AVGO"]},
            "Healthcare": {"change_pct": 0.3, "leaders": ["UNH", "JNJ"]},
            "Energy": {"change_pct": -0.8, "laggards": ["XOM", "CVX"]},
            "Financials": {"change_pct": 0.6, "leaders": ["JPM", "BAC"]},
            "Consumer Discretionary": {"change_pct": -0.4, "laggards": ["DG", "TGT"]},
            "Communication Services": {"change_pct": 0.9, "leaders": ["META", "GOOGL"]},
        },
        "vix": 14.5,
        "dollar_index": 106.2,
        "us_10y_yield": 4.08,
        "crude_oil_wti": 68.5,
        "gold": 2650.3,
    }
    
    # Save all sample data
    with open(output_dir / 'macro_data.json', 'w', encoding='utf-8') as f:
        json.dump(macro_data, f, indent=2, ensure_ascii=False)
    
    with open(output_dir / 'earnings_data.json', 'w', encoding='utf-8') as f:
        json.dump(earnings_data, f, indent=2, ensure_ascii=False)
    
    with open(output_dir / 'news_data.json', 'w', encoding='utf-8') as f:
        json.dump(news_data, f, indent=2, ensure_ascii=False)
    
    with open(output_dir / 'calendar_events.json', 'w', encoding='utf-8') as f:
        json.dump(calendar_events, f, indent=2, ensure_ascii=False)
    
    with open(output_dir / 'fomc_events.json', 'w', encoding='utf-8') as f:
        json.dump(fomc_events, f, indent=2, ensure_ascii=False)
    
    with open(output_dir / 'market_summary.json', 'w', encoding='utf-8') as f:
        json.dump(market_summary, f, indent=2, ensure_ascii=False)
    
    logger.info(f"Sample source data created at: {output_dir}")
    print(f"✓ Sample source data created at: {output_dir}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test data loading")
    parser.add_argument(
        "--source-path",
        default="econ_briefing/data",
        help="Path to source data directory"
    )
    parser.add_argument(
        "--create-sample",
        action="store_true",
        help="Create sample data instead of loading"
    )
    
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO)
    
    if args.create_sample:
        create_sample_source_data(args.source_path)
    else:
        loader = ClosingBriefingDataLoader(args.source_path)
        sources = loader.load_all_sources()
        
        print("\n📊 Loaded Data Summary:")
        for key, value in sources.items():
            if isinstance(value, list):
                print(f"  {key}: {len(value)} items")
            elif isinstance(value, dict):
                print(f"  {key}: {len(value)} keys")
