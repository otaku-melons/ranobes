from Source.Core.Base.SourceOperator import BaseSourceOperator

from datetime import datetime
from time import sleep

from bs4 import BeautifulSoup, Tag
import dateparser

class SourceOperator(BaseSourceOperator):
	"""Оператор источника."""

	#==========================================================================================#
	# >>>>> ПРИВАТНЫЕ МЕТОДЫ КОЛЛЕКЦИОНИРОВАНИЯ <<<<< #
	#==========================================================================================#

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
		Now = datetime.now()

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

	#==========================================================================================#
	# >>>>> ПУБЛИЧНЫЕ МЕТОДЫ <<<<< #
	#==========================================================================================#

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