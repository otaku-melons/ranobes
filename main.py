from Source.Core.Base.Formats.Ranobe import Branch, Chapter, ChaptersTypes, Ranobe
from Source.Core.Base.Parsers.RanobeParser import RanobeParser
from Source.Core.Base.Formats.BaseFormat import Statuses

from dublib.Methods.Data import RemoveRecurringSubstrings
from dublib.Polyglot import HTML

from time import sleep

from recognizers_number import recognize_number, Culture
from bs4 import BeautifulSoup

class Parser(RanobeParser):
	"""Парсер."""
	
	#==========================================================================================#
	# >>>>> ПЕРЕОПРЕДЕЛЯЕМЫЕ МЕТОДЫ <<<<< #
	#==========================================================================================#

	def __BuildImageLink(self, src: str) -> str:
		"""
		Строит полную ссылку из источника.

		:param src: Источник изображения.
		:type src: str
		:return: Полная ссылка.
		:rtype: str
		"""

		if src.startswith("http"): return src
		return f"https://{self._Manifest.site}/" + src.lstrip("/")

	def __ReplaceNumberFromChapterName(self, name: str, number: str) -> str:
		"""
		Уадляет часть с номером главы/тома из названия.

		:param name: Полное название главы.
		:type name: str
		:param number: Номер главы или тома для разбивки.
		:type number: str
		:return: Обработанное название главы.
		:rtype: str
		"""

		if number:
			Buffer = list()

			Buffer = name.split(number)
			Buffer = Buffer[1:]
			name = number.join(Buffer)
			name = name.strip()

			if name and not name[0].isalpha(): name = name.lstrip("-.–")

		return name

	def __CheckChapterType(self, fullname: str, name: str) -> ChaptersTypes | None:
		"""
		Пытается определить тип главы.

		:param fullname: Полное название главы.
		:type fullname: str
		:param name: Часть названия главы без номера тома и номера главы.
		:type name: str
		:return: Тип главы.
		:rtype: ChaptersTypes | None
		"""

		fullname = fullname.lower()
		name = name.lower()

		#---> afterword
		#==========================================================================================#
		if "послесловие" in name: return ChaptersTypes.afterword

		#---> art
		#==========================================================================================#
		if name.startswith("начальные") and "иллюстрации" in name: return ChaptersTypes.art

		#---> epilogue
		#==========================================================================================#
		if "эпилог" in name: return ChaptersTypes.epilogue

		#---> extra
		#==========================================================================================#
		if name.startswith("дополнительн") and "истори" in name: return ChaptersTypes.extra
		if name.startswith("бонус") and "истори" in name: return ChaptersTypes.extra
		if name.startswith("экстра"): return ChaptersTypes.extra
		if "глава" not in fullname and "том" in fullname: return ChaptersTypes.extra

		#---> glossary
		#==========================================================================================#
		if name.startswith("глоссарий"): return ChaptersTypes.glossary

		#---> prologue
		#==========================================================================================#
		if "пролог" in name: return ChaptersTypes.prologue

		#---> trash
		#==========================================================================================#
		if name.startswith("реквизиты") and "переводчик" in name: return ChaptersTypes.trash
		if name.startswith("примечани") and "переводчик" in name: return ChaptersTypes.trash

		#---> chapter
		#==========================================================================================#
		if "глава" in fullname: return ChaptersTypes.chapter

		return None

	def __GetFromSlugID(self) -> int | None:
		"""
		Пытается получить ID тайтла из алиаса.

		:return: ID тайтла.
		:rtype: int | None
		"""

		try: return int(self._Title.slug.split("-")[0])
		except ValueError: pass

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
			Response = self._Requestor.get(f"{ChaptersLink}page/{Page}/")
			Soup = BeautifulSoup(Response.text, "html.parser")

			if Response.status_code == 200:
				Lines = Soup.find_all("div", {"class": "cat_block cat_line"})
				
				for Line in Lines:
					Link: str = Line.find("a")["href"]
					Name: str = Line.find("h6").get_text()
					ChapterSlug = Link.split("/")[-1][:-5]
					ChapterID = int(ChapterSlug.split("-")[0])

					Results = recognize_number(Name, Culture.English)

					ChapterVolume = None
					ChapterNumber = None

					for Index in range(len(Results)):
						NameWords = tuple(Part.lower() for Part in Name.split())
						HasVolume = "том" in NameWords
						HasChapter = "глава" in NameWords

						if Index == 0 and HasVolume: ChapterVolume = Results[Index].resolution["value"]
						elif HasChapter: ChapterNumber = Results[Index].resolution["value"]

						Index += 1

					if ChapterVolume or ChapterNumber: Name = self.__ReplaceNumberFromChapterName(Name, ChapterNumber or ChapterVolume)

					Buffer = Chapter(self._SystemObjects, self._Title)
					Buffer.set_id(ChapterID)
					Buffer.set_slug(ChapterSlug)
					Buffer.set_name(Name)
					Buffer.set_number(ChapterNumber)
					Buffer.set_volume(ChapterVolume)
					Buffer.set_type(self.__CheckChapterType(Line.find("h6").get_text(), Name))
					Buffer.set_is_paid(False)

					BranchObject.add_chapter(Buffer)

				self._Portals.info(f"Chapters data collected on page {Page}.")
				sleep(self._Settings.common.delay)
				Page += 1

			elif Response.status_code == 404: break
			else: self._Portals.request_error(Response, "Unable request chapters page.")

		self._Title.add_branch(BranchObject)

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
			Soup = BeautifulSoup(Response.text, "html.parser")
			Container = Soup.find("div", {"id": "arrticle"})

			Scripts = Container.find_all("script")
			for Script in Scripts: Script.decompose()
			ParagraphsBlocks = Container.find_all("p", recursive = False)

			for Index in range(len(ParagraphsBlocks)):
				ImagesBlocks = ParagraphsBlocks[Index].find_all("img")

				for Div in ParagraphsBlocks[Index].find_all("div", {"align": "center"}): Div.decompose()

				if not ParagraphsBlocks[Index].get_text().strip() and ImagesBlocks:
					Images = "".join(tuple(f"<img src=\"" + self.__BuildImageLink(Block["src"]) + "\">" for Block in ImagesBlocks))
					ParagraphsBlocks[Index] = BeautifulSoup(f"<p>{Images}</p>", "html.parser")

				elif ImagesBlocks:
					for Block in ImagesBlocks:
						Block.attrs = {"src": self.__BuildImageLink(Block["src"])}

				Paragraphs.append(str(ParagraphsBlocks[Index]))
			
		elif Response.status_code == 404: self._Portals.chapter_not_found(self._Title, chapter)
		else: self._Portals.request_error(Response, "Unable request chapter.")

		return Paragraphs

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

		for Paragraph in self.__GetParagraphs(chapter): chapter.add_paragraph(Paragraph)
	
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

