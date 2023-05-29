__all__ = ['LinkPreview', 'TelegramPost', 'TelegramChannel', 'TelegramChannelScraper']


import bs4
import dataclasses
import datetime
import logging
import re
import snscrape.base
import snscrape.utils
import typing
import urllib.parse


_logger = logging.getLogger(__name__)
_SINGLE_MEDIA_LINK_PATTERN = re.compile(r'^https://t\.me/[^/]+/\d+\?single$')


@dataclasses.dataclass
class LinkPreview:
	href: str
	siteName: typing.Optional[str] = None
	title: typing.Optional[str] = None
	description: typing.Optional[str] = None
	image: typing.Optional[str] = None


@dataclasses.dataclass
class TelegramPost(snscrape.base.Item):
	url: str
	date: datetime.datetime
	content: str
	outlinks: list
	views: str
	user: str
	author: str
	forward_from: str
	forward_url: str
	photos: list
	videos: list
	reply: list
	linkPreview: typing.Optional[LinkPreview] = None

	outlinksss = snscrape.base._DeprecatedProperty('outlinksss', lambda self: ' '.join(self.outlinks), 'outlinks')

	def __str__(self):
		return self.url


@dataclasses.dataclass
class TelegramChannel(snscrape.base.Item):
	username: str
	title: str
	verified: bool
	photo: str
	description: typing.Optional[str] = None
	members: typing.Optional[snscrape.base.IntWithGranularity] = None
	photos: typing.Optional[snscrape.base.IntWithGranularity] = None
	video: typing.Optional[snscrape.base.IntWithGranularity] = None
	links: typing.Optional[snscrape.base.IntWithGranularity] = None
	files: typing.Optional[snscrape.base.IntWithGranularity] = None

	def __str__(self):
		return f'https://t.me/s/{self.username}'


class TelegramChannelScraper(snscrape.base.Scraper):
	name = 'telegram-channel'

	def __init__(self, name, info = False, **kwargs):
		super().__init__(**kwargs)
		self._name = name
		self._headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/101.0.4044.138 Safari/537.36'}
		self._initialPage = None
		self._initialPageSoup = None
		self.info = info

	def _initial_page(self):
		if self._initialPage is None:
			r = self._get(f'https://t.me/s/{self._name}', headers = self._headers)
			if r.status_code != 200:
				raise snscrape.base.ScraperException(f'Got status code {r.status_code}')
			self._initialPage, self._initialPageSoup = r, bs4.BeautifulSoup(r.text, 'lxml')
		return self._initialPage, self._initialPageSoup

	def _soup_to_items(self, soup, pageUrl, onlyUsername = False):
		posts = soup.find_all('div', attrs = {'class': 'tgme_widget_message', 'data-post': True})
		for post in reversed(posts):
			if onlyUsername:
				yield post['data-post'].split('/')[0]
				return
			dateDiv = post.find('div', class_ = 'tgme_widget_message_footer').find('a', class_ = 'tgme_widget_message_date')
			rawUrl = dateDiv['href']
			if not rawUrl.startswith('https://t.me/') or sum(x == '/' for x in rawUrl) != 4 or rawUrl.rsplit('/', 1)[1].strip('0123456789') != '':
				_logger.warning(f'Possibly incorrect URL: {rawUrl!r}')
			if (viewDiv := post.find('div', class_ = 'tgme_widget_message_footer').find('span', class_ = 'tgme_widget_message_views')):
				views = viewDiv.text
			else:
				views = '0'
			url = rawUrl.replace('//t.me/', '//t.me/s/')
			date = datetime.datetime.strptime(dateDiv.find('time', datetime = True)['datetime'].replace('-', '', 2).replace(':', ''), '%Y%m%dT%H%M%S%z')
			if (reply := post.find('a', class_ = 'tgme_widget_message_reply')):
				_ru = reply.attrs.get('href', None)
				if (_rt := reply.find('div', class_ = 'tgme_widget_message_text')):
					_rt = _rt.text
				reply = [_ru, _rt]
			else:
				reply = []
			message = post.select('div.tgme_widget_message_text.js-message_text')
			if len(message) > 0:
				message = message[0]
				content = message.text
				outlinks = []
				user = None
				author = None
				forward_from = None
				forward_url = None
				photos = []
				videos = []
				for link in post.find_all('a'):
					if 'tgme_widget_message_user'in link.parent.attrs.get('class', []):
						user = link['href']
						continue
					if 'tgme_widget_message_author'in link.parent.attrs.get('class', []):
						if (_span := link.find('span')):
							author = _span.text
							continue
					if 'tgme_widget_message_forwarded_from'in link.parent.attrs.get('class', []):
						forward_url = link['href']
						if (_span := link.find('span')):
							forward_from = _span.text
						continue
					if 'tgme_widget_message_photo_wrap' in link.attrs.get('class', []):
						_style = link.attrs.get('style')
						_photo = re.sub(r".*url\('(http.*)'\)", r'\1', _style)
						photos.append(_photo)
						continue
					if (_videos := link.find('div', class_ = 'tgme_widget_message_video_wrap')):
						if (_video := _videos.find('video')):
							_video = _video.attrs.get('src')
							videos.append(_video)
							continue
					if (_videos := link.find('i', class_ = 'tgme_widget_message_video_thumb')):
						_style = _videos.attrs.get('style')
						_video = re.sub(r".*url\('(http.*)'\)", r'\1', _style)
						photos.append(_video)
					if link['href'] == rawUrl or link['href'] == url:
						# Generic filter of links to the post itself, catches videos, photos, and the date link
						continue
					if _SINGLE_MEDIA_LINK_PATTERN.match(link['href']):
						# Individual photo or video link
						continue
					href = urllib.parse.urljoin(pageUrl, link['href'])
					if href not in outlinks:
						outlinks.append(href)
			else:
				user = None
				author = None
				forward_from = None
				forward_url = None
				photos = []
				videos = []
				content = None
				outlinks = []
			linkPreview = None
			if (linkPreviewA := post.find('a', class_ = 'tgme_widget_message_link_preview')):
				kwargs = {}
				kwargs['href'] = urllib.parse.urljoin(pageUrl, linkPreviewA['href'])
				if (siteNameDiv := linkPreviewA.find('div', class_ = 'link_preview_site_name')):
					kwargs['siteName'] = siteNameDiv.text
				if (titleDiv := linkPreviewA.find('div', class_ = 'link_preview_title')):
					kwargs['title'] = titleDiv.text
				if (descriptionDiv := linkPreviewA.find('div', class_ = 'link_preview_description')):
					kwargs['description'] = descriptionDiv.text
				if (imageI := linkPreviewA.find('i', class_ = 'link_preview_image')):
					if imageI['style'].startswith("background-image:url('"):
						kwargs['image'] = imageI['style'][22 : imageI['style'].index("'", 22)]
					else:
						_logger.warning(f'Could not process link preview image on {url}')
				elif (imageI := linkPreviewA.find('i', class_ = 'link_preview_right_image')):
					if imageI['style'].startswith("background-image:url('"):
						kwargs['image'] = imageI['style'][22 : imageI['style'].index("'", 22)]
					else:
						_logger.warning(f'Could not process link preview right image on {url}')
				linkPreview = LinkPreview(**kwargs)
			yield TelegramPost(url = url, date = date, content = content, outlinks = outlinks, views = views, user = user, author = author, forward_from = forward_from, forward_url = forward_url, photos = photos, videos = videos, reply = reply, linkPreview = linkPreview)

	def get_items(self):
		if self.info:
			yield self._get_entity()
			return
		r, soup = self._initial_page()
		if '/s/' not in r.url:
			_logger.warning('No public post list for this user')
			return
		while True:
			yield from self._soup_to_items(soup, r.url)
			pageLink = soup.find('a', attrs = {'class': 'tme_messages_more', 'data-before': True})
			if not pageLink:
				break
			nextPageUrl = urllib.parse.urljoin(r.url, pageLink['href'])
			r = self._get(nextPageUrl, headers = self._headers)
			if r.status_code != 200:
				raise snscrape.base.ScraperException(f'Got status code {r.status_code}')
			soup = bs4.BeautifulSoup(r.text, 'lxml')

	def _get_entity(self):
		kwargs = {}
		# /channel has a more accurate member count and bigger profile picture
		r = self._get(f'https://t.me/{self._name}', headers = self._headers)
		if r.status_code != 200:
			raise snscrape.base.ScraperException(f'Got status code {r.status_code}')
		soup = bs4.BeautifulSoup(r.text, 'lxml')
		membersDiv = soup.find('div', class_ = 'tgme_page_extra')
		if membersDiv.text.endswith(' subscribers'):
			kwargs['members'] = int(membersDiv.text[:-12].replace(' ', ''))
		kwargs['photo'] = soup.find('img', class_ = 'tgme_page_photo_image').attrs['src']

		r, soup = self._initial_page()
		if '/s/' not in r.url: # Redirect on channels without public posts
			return
		channelInfoDiv = soup.find('div', class_ = 'tgme_channel_info')
		assert channelInfoDiv, 'channel info div not found'
		titleDiv = channelInfoDiv.find('div', class_ = 'tgme_channel_info_header_title')
		kwargs['title'] = titleDiv.find('span').text
		kwargs['verified'] = bool(titleDiv.find('i', class_ = 'verified-icon'))
		# The username in the channel info is not canonicalised, nor is the one on the /channel page anywhere.
		# However, the post URLs are, so extract the first post and use that.
		try:
			kwargs['username'] = next(self._soup_to_items(soup, r.url, onlyUsername = True))
		except StopIteration:
			# If there are no posts, fall back to the channel info div, although that should never happen due to the 'Channel created' entry.
			_logger.warning('Could not find a post; extracting username from channel info div, which may not be capitalised correctly')
			kwargs['username'] = channelInfoDiv.find('div', class_ = 'tgme_channel_info_header_username').text[1:] # Remove @
		if (descriptionDiv := channelInfoDiv.find('div', class_ = 'tgme_channel_info_description')):
			kwargs['description'] = descriptionDiv.text

		def parse_num(s):
			s = s.replace(' ', '')
			if s.endswith('M'):
				return int(float(s[:-1]) * 1e6), 10 ** (6 if '.' not in s else 6 - len(s[:-1].split('.')[1]))
			elif s.endswith('K'):
				return int(float(s[:-1]) * 1000), 10 ** (3 if '.' not in s else 3 - len(s[:-1].split('.')[1]))
			else:
				return int(s), 1

		for div in channelInfoDiv.find_all('div', class_ = 'tgme_channel_info_counter'):
			value, granularity = parse_num(div.find('span', class_ = 'counter_value').text)
			type_ = div.find('span', class_ = 'counter_type').text
			if type_ == 'subscribers':
				# Already extracted more accurately from /channel, skip
				kwargs['members'] = snscrape.base.IntWithGranularity(value, granularity)
			elif type_ in ('photos', 'video', 'links', 'files'):
				kwargs[type_] = snscrape.base.IntWithGranularity(value, granularity)

		return TelegramChannel(**kwargs)

	@classmethod
	def _cli_setup_parser(cls, subparser):
		subparser.add_argument('channel', type = snscrape.utils.nonempty_string_arg('channel'), help = 'A channel name')
		subparser.add_argument('--info', action = 'store_true', default = False, help = 'only get channel info')

	@classmethod
	def _cli_from_args(cls, args):
		return cls._cli_construct(args, args.channel, info = args.info)
