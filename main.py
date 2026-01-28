from Source.Core.Base.Formats.Ranobe import Branch, Chapter, ChapterHeaderParser
from Source.Core.Base.Parsers.RanobeParser import RanobeParser
from Source.Core.Base.Formats.BaseFormat import Statuses

from dublib.Methods.Data import RemoveRecurringSubstrings
from dublib.Polyglot import HTML

from time import sleep
import datetime

from bs4 import BeautifulSoup, Tag
import dateparser

class Parser(RanobeParser):
	"""Парсер."""

	#==========================================================================================#
	# >>>>> ПРИВАТНЫЕ МЕТОДЫ <<<<< #
	#==========================================================================================#

	def __BuildFullLink(self, link: str) -> str:
		"""
		Строит полную ссылку.

		:param link: Ссылка.
		:type link: str
		:return: Полная ссылка.
		:rtype: str
		"""

		if link.startswith("http"): return link
		return f"https://{self._Manifest.site}/" + link.lstrip("/")

	def __CollectUpdates(self, pages: int | None, period: int | None) -> tuple[str]:
		"""
		Собирает алиасы тайтлов из каталога по заданным параметрам.

		:param pages: Количество запрашиваемых страниц каталога.
		:type pages: int | None
		:param period: Количество часов до текущего момента, составляющее период получения данных.
		:type period: int | None
		:return: Набор собранных алиасов.
		:rtype: tuple[str]
		"""

		IsCollected = False
		Page = 1
		Slugs = list()
		Now = datetime.datetime.now()

		while not IsCollected:
			Response = self._Requestor.get(f"https://{self._Manifest.site}/updates/page/{Page}/")
			if not Response.ok: self._Portals.request_error(Response, f"Unable get updates page {Page}.")

			Soup = BeautifulSoup(Response.text, "html.parser")
			Main = Soup.find("main")
			UpdatesBlocks: list[Tag] = list()
			if Main: UpdatesBlocks = Main.find_all("div", {"class": "block story_line story_line-img"})
			if not UpdatesBlocks: IsCollected = True

			for Block in UpdatesBlocks:
				PublicationDate = Block.find("span", {"class": "small grey"})
				PublicationDate = dateparser.parse(PublicationDate.get_text())
				Delta = Now - PublicationDate

				if not period: continue

				if Delta.total_seconds() / 3600 <= period:
					Link = Block.find("a")["href"]
					Slug = self.__GetFullSlug(Link)
					Slugs.append(Slug)

				else:
					IsCollected = True
					break

			self._Portals.collect_progress_by_page(Page)
			sleep(self._Settings.common.delay)
			if pages and Page >= pages: IsCollected = True
			Page += 1

		return tuple(set(Slugs))

	def __GetFromSlugID(self) -> int | None:
		"""
		Пытается получить ID тайтла из алиаса.

		:return: ID тайтла.
		:rtype: int | None
		"""

		try: return int(self._Title.slug.split("-")[0])
		except ValueError: pass

	def __GetFullSlug(self, link: str) -> str:
		"""
		Получает полный алиас по части из URI главы.

		:param link: Часть алиаса из URI главы.
		:type link: str
		:return: Полный алиас.
		:rtype: str
		"""

		Response = self._Requestor.get(link)
		if not Response.ok: self._Portals.request_error(Response, f"Unable get full slug for chapter: \"{link}\".")
		
		Soup = BeautifulSoup(Response.text, "html.parser")
		BookLink = Soup.find("div", {"class": "category grey ellipses"})
		if not BookLink: self._Portals.error("Book link not found.")
		sleep(self._Settings.common.delay)

		return BookLink.find("a")["href"].split("/")[-1][:-5]

	def __GetParagraphs(self, chapter: Chapter) -> tuple[str]:
		"""
		Получает абзацы в главе.

		:param chapter: Данные главы.
		:type chapter: Chapter
		:return: Последовательность абзацев главы.
		:rtype: tuple[str]
		"""

		Paragraphs = list()
		Response = self._Requestor.get(f"https://{self._Manifest.site}/chapters/{self._Title.slug}/{chapter.slug}.html")

		if Response.status_code == 200:
			Soup = BeautifulSoup(Response.text, "lxml")
			Container = Soup.find("div", {"id": "arrticle"})
			for Script in Container.find_all("script"): Script.decompose()
			ParagraphsBlocks = Container.find_all("p", recursive = False)

			# Некоторые страницы не содержат тегов абзацев.
			if not ParagraphsBlocks and Container.find("br"):
				PlainContent = Container.decode_contents()
				ParagraphsBuffer = PlainContent.split("<br/>")
				ParagraphsBlocks = list()

				for Line in ParagraphsBuffer:
					Line = Line.strip()
					if not Line: continue
					ParagraphsBlocks.append(BeautifulSoup(f"<p>{Line}</p>", "html.parser"))

			for Index in range(len(ParagraphsBlocks)):
				ImagesBlocks = ParagraphsBlocks[Index].find_all("img")

				for Div in ParagraphsBlocks[Index].find_all("div", {"align": "center"}): Div.decompose()

				if not ParagraphsBlocks[Index].get_text().strip() and ImagesBlocks:
					Images = "".join(tuple(f"<img src=\"" + self.__BuildFullLink(Block["src"]) + "\">" for Block in ImagesBlocks))
					ParagraphsBlocks[Index] = BeautifulSoup(f"<p>{Images}</p>", "html.parser")

				elif ImagesBlocks:
					for Block in ImagesBlocks:
						Block.attrs = {"src": self.__BuildFullLink(Block["src"])}

				Paragraphs.append(str(ParagraphsBlocks[Index]))
			
		elif Response.status_code == 404: self._Portals.chapter_not_found(self._Title, chapter)
		else: self._Portals.request_error(Response, "Unable request chapter.")

		return Paragraphs

	def __ParseCover(self, soup: BeautifulSoup):
		"""
		Парсит данные обложки.

		:param soup: HTML код страницы.
		:type soup: BeautifulSoup
		"""

		self._Title.add_cover(f"https://{self._Manifest.site}" + soup.find("div", {"class": "poster"}).find("img")["src"])

	def __ParseAuthors(self, soup: BeautifulSoup):
		"""
		Парсит авторов.

		:param soup: HTML код страницы.
		:type soup: BeautifulSoup
		"""

		for Block in soup.find("span", {"itemprop": "creator"}).find_all("a"):
			self._Title.add_author(Block.get_text())

	def __ParseDescription(self, soup: BeautifulSoup):
		"""
		Парсит описание.

		:param soup: HTML код страницы.
		:type soup: BeautifulSoup
		"""

		DescriptionBlock = soup.find("div", {"itemprop": "description"})
		StyleBlock = DescriptionBlock.find("style")
		if StyleBlock: StyleBlock.decompose()

		Description = DescriptionBlock.decode_contents()
		Description = Description.split("<br/>")
		Description = tuple(String.strip() for String in Description)
		Description = HTML("\n".join(Description)).plain_text
		Description = Description.replace("\t", "")
		Description = RemoveRecurringSubstrings(Description, "\n")
		Description = Description[:-27]
		
		self._Title.set_description(Description)

	def __ParseOriginalLanguage(self, soup: BeautifulSoup):
		"""
		Парсит язык оригинала по стандарту ISO 639-3.

		:param soup: HTML код страницы.
		:type soup: BeautifulSoup
		"""

		Language = soup.find("span", {"itemprop": "locationCreated"}).find("a").get_text()

		LanguagesCodes = {
			"Китайский": "zho",
			"Корейский": "kor",
			"Русский": "rus",
			"Японский": "jpn",
			"Английский": "eng",
		}
		
		self._Title.set_original_language(LanguagesCodes[Language])

	def __ParseStatus(self, soup: BeautifulSoup):
		"""
		Парсит статус тайтла.

		:param soup: HTML код страницы.
		:type soup: BeautifulSoup
		"""

		Status = soup.find("li", {"title": "Статус перевода на русский."}).find("a").get_text()

		Determinations = {
			"Активен": Statuses.ongoing,
			"Завершено": Statuses.completed,
			"В ожидании глав": Statuses.ongoing,
			"Не активен": Statuses.dropped
		}
		
		self._Title.set_status(Determinations[Status])

	def __ParseGenres(self, soup: BeautifulSoup):
		"""
		Парсит жанры.

		:param soup: HTML код страницы.
		:type soup: BeautifulSoup
		"""

		GenresBlocks = soup.find("div", {"itemprop": "genre"}).find_all("a")
		for Block in GenresBlocks: self._Title.add_genre(Block.get_text())

	def __ParseTags(self, soup: BeautifulSoup):
		"""
		Парсит теги.

		:param soup: HTML код страницы.
		:type soup: BeautifulSoup
		"""

		GenresBlocks = soup.find("div", {"itemprop": "keywords"}).find_all("a")
		for Block in GenresBlocks: self._Title.add_tag(Block.get_text())

	def __ParseBranch(self, soup: BeautifulSoup):
		"""
		Парсит данные ветви.

		:param soup: HTML код страницы.
		:type soup: BeautifulSoup
		"""

		BranchObject = Branch(self._Title.id)
		Page = 1

		ChaptersLink = soup.find("a", {"title": "Перейти в оглавление"})["href"]

		while True:
			Response = self._Requestor.get(self.__BuildFullLink(f"{ChaptersLink}page/{Page}/"))
			Soup = BeautifulSoup(Response.text, "html.parser")

			if Response.status_code == 200:
				Lines = Soup.find_all("div", {"class": "cat_block cat_line"})
				
				for Line in Lines:
					Link: str = Line.find("a")["href"]
					ChapterHeader: str = Line.find("h6").get_text()
					ChapterSlug = Link.split("/")[-1][:-5]
					ChapterID = int(ChapterSlug.split("-")[0])
					HeaderData = ChapterHeaderParser(ChapterHeader, self._Title).parse()

					Buffer = Chapter(self._SystemObjects, self._Title)
					Buffer.set_id(ChapterID)
					Buffer.set_slug(ChapterSlug)
					Buffer.set_name(HeaderData.name)
					Buffer.set_number(HeaderData.number)
					Buffer.set_volume(HeaderData.volume)
					Buffer.set_type(HeaderData.type)
					Buffer.set_is_paid(False)
					BranchObject.add_chapter(Buffer)

				self._Portals.info(f"Chapters data collected on page {Page}.")
				sleep(self._Settings.common.delay)
				Page += 1

			elif Response.status_code == 404: break
			else: self._Portals.request_error(Response, "Unable request chapters page.")

		BranchObject.reverse()
		self._Title.add_branch(BranchObject)

	#==========================================================================================#
	# >>>>> ПУБЛИЧНЫЕ МЕТОДЫ <<<<< #
	#==========================================================================================#

	def amend(self, branch: Branch, chapter: Chapter):
		"""
		Дополняет главу дайными о слайдах.

		:param branch: Данные ветви.
		:type branch: Branch
		:param chapter: Данные главы.
		:type chapter: Chapter
		"""

		chapter.set_paragraphs(self.__GetParagraphs(chapter))
	
	def collect(self, period: int | None = None, filters: str | None = None, pages: int | None = None) -> tuple[str]:
		"""
		Собирает список алиасов тайтлов по заданным параметрам.

		:param period: Количество часов до текущего момента, составляющее период получения данных.
		:type period: int | None
		:param filters: Строка, описывающая фильтрацию (подробнее в README.md парсера).
		:type filters: str | None
		:param pages: Количество запрашиваемых страниц каталога.
		:type pages: int | None
		:return: Набор собранных алиасов.
		:rtype: tuple[str]
		"""

		if filters: self._Portals.error("Filters not supported in collecting.")

		return self.__CollectUpdates(pages, period)

	def parse(self):
		"""Получает основные данные тайтла."""

		Response = self._Requestor.get(f"https://{self._Manifest.site}/ranobe/{self._Title.slug}.html")

		if Response.status_code == 200:
			Soup = BeautifulSoup(Response.text, "html.parser")
			
			self._Title.set_id(self.__GetFromSlugID())
			self._Title.set_content_language("rus")

			Names = Soup.find("h1", {"itemprop": "headline"}).get_text().split("•")
			Names = tuple(filter(lambda Value: Value.strip(), Names))
			Names = tuple(Value.strip() for Value in Names)
			self._Title.set_localized_name(Names[0])
			self._Title.set_eng_name(Names[1])
			if len(Names) > 2: self._Title.set_another_names(Names[2:])

			self.__ParseCover(Soup)
			self.__ParseAuthors(Soup)
			self._Title.set_publication_year(Soup.find("span", {"itemprop": "dateCreated"}).find("a").get_text())
			self.__ParseDescription(Soup)
			self.__ParseOriginalLanguage(Soup)
			self.__ParseStatus(Soup)
			self._Title.set_is_licensed(False)
			self.__ParseGenres(Soup)
			self.__ParseTags(Soup)
			self.__ParseBranch(Soup)

		elif Response.status_code == 404: self._Portals.title_not_found(self._Title)
		else: self._Portals.request_error(Response, "Unable request title page.")