import requests
import json

from theExceptions import (CreationError, DeletionError, UpdateError, ConstraintViolation, SchemaViolation, ValidationError)

class Document(object) :

	def __init__(self, collection, jsonFieldInit = {}) :
		self.reset(collection, jsonFieldInit)

	def reset(self, collection, jsonFieldInit = {}) :
		self.collection = collection
		self.documentsURL = self.collection.documentsURL
		
		self._store = {}
		self._patchStore = {}

		self.set(jsonFieldInit)
		self.modified = True

	def setPrivates(self, fieldDict) :
		try :
			self._id = fieldDict["_id"]
			self.URL = "%s/%s" % (self.documentsURL, self._id)
			del(fieldDict["_id"])
			
			self._rev = fieldDict["_rev"]
			del(fieldDict["_rev"])
		
			self._key = fieldDict["_key"]
			del(fieldDict["_key"])
		except KeyError :
			self._id, self._rev, self._key = None, None, None
			self.URL = None

	def set(self, fieldDict) :
		"""Sets the document according to values contained in the dictinnary fieldDict. This will also set self._id/_rev/_key"""

		self.setPrivates(fieldDict)

		if self.collection._validation['on_set']:
			for k in fieldDict.keys() :
				self[k] = fieldDict[k]
		else :
			self._store.update(fieldDict)

	def save(self, **docArgs) :
		"""Either performs a POST (for a new document) or a PUT (complete document overwrite).
		If you want to only update the modified fields use the .path() function.
		Use docArgs to put things such as 'waitForSync = True'.
		It will only trigger a saving of the document if it has been modified since the last save. If you want to force the saving you can use forceSave()"""

		if self.modified :
			if self.collection._validation['on_save'] :
				self.validate(patch = False, logErrors = False)

			params = dict(docArgs)
			params.update({'collection': self.collection.name })
			payload = json.dumps(self._store)

			if self.URL is None :
				r = requests.post(self.documentsURL, params = params, data = payload)
				update = False
			else :
				r = requests.put(self.URL, params = params, data = payload)
				update = True

			data = r.json()
			if (r.status_code == 201 or r.status_code == 202) and not data['error'] :
				if update :
					self._rev = data['_rev']
				else :
					self.setPrivates(data)
			else :
				if update :
					raise UpdateError(data['errorMessage'], data)
				else :
					raise CreationError(data['errorMessage'], data)

			self.modified = False

	def forceSave(self, **docArgs) :
		"saves even if the document has not been modified since the last save"
		self.modified = True
		self.save(**docArgs)

	def saveCopy(self) :
		"saves a copy of the object and become that copy. returns a tuple (old _key, new _key)"
		old_key = self._key
		self.reset(self.collection)
		self.save()
		return (old_key, self._key)

	def patch(self, keepNull = True, **docArgs) :
		"""Updates only the modified fields.
		The default behaviour concening the keepNull parameter is the opposite of ArangoDB's default, Null values won't be ignored
		Use docArgs for things such as waitForSync = True"""

		if self.collection._validation['on_save'] :
			self.validate(patch = True, logErrors = False)

		if self.URL is None :
			raise ValueError("Cannot patch a document that was not previously saved")
		
		if len(self._patchStore) > 0 :
			params = dict(docArgs)
			params.update({'collection': self.collection.name, 'keepNull' : keepNull})
			payload = json.dumps(self._patchStore)
			
			r = requests.patch(self.URL, params = params, data = payload)
			data = r.json()
			if (r.status_code == 201 or r.status_code == 202) and not data['error'] :
				self._rev = data['_rev']
			else :
				raise UpdateError(data['errorMessage'], data)

			self.modified = False

	def delete(self) :
		if self.URL is None :
			raise DeletionError("Can't delete a document that was not saved") 
		r = requests.delete(self.URL)
		data = r.json()
		if (r.status_code != 200 and r.status_code != 202) or data['error'] :
			raise DeletionError(data['errorMessage'], data)
		self.reset(self.collection)

		self.modified = True

	def validate(self, patch = False) :
		"validates either the whole store, or only the patch store( patch = True) of the document according to the collection's settings.If logErrors returns a dictionary of errros per field, else raises exceptions"
		if patch :
			return self.collection._validateDct(self._patchStore)
		else :
			return self.collection._validateDct(self._store)

	def getInEdges(self, edges, rawResults = False) :
		"An alias for getEdges() that returns only the in Edges"
		return self.getEdges(edges, inEdges = True, outEdges = False, rawResults = rawResults)
		
	def getOutEdges(self, edges, rawResults = False) :
		"An alias for getEdges() that returns only the out Edges"
		return self.getEdges(edges, inEdges = False, outEdges = True, rawResults = rawResults)

	def getEdges(self, edges, inEdges = True, outEdges = True, rawResults = False) :
		"""returns in, out, or both edges linked to self belonging the collection 'edges'.
		If rawResults a arango results will be return as fetched, if false, will return a liste of Edge objects"""
		try :
			return edges.getEdges(self, inEdges, outEdges, rawResults)
		except AttributeError :
			raise AttributeError("%s does not seem to be a valid Edges object" % edges)

	def __getitem__(self, k) :
		if self.collection._validation['allow_foreign_fields'] :
			return self._store.get(k)
		try :
			return self._store[k]
		except KeyError :
			raise KeyError("Document has no field %s, for a permissive behaviour set 'allow_foreign_fields' to True" % k)

	def __setitem__(self, k, v) :
		if self.collection._validation['on_set'] :
			self.collection.validateField(k, v)

		self._store[k] = v
		if self.URL is not None :
			self._patchStore[k] = self._store[k]
		
		self.modified = True

	def __str__(self) :
		return 'ArangoDoc: ' + str(self._store)

	def __repr__(self) :
		return 'ArangoDoc: ' + repr(self._store)

class Edge(Document) :

	def __init__(self, edgeCollection, jsonFieldInit = {}) :
		self.reset(edgeCollection, jsonFieldInit)

	def reset(self, edgeCollection, jsonFieldInit = {}) :
		Document.reset(self, edgeCollection, jsonFieldInit)

	def setPrivates(self, jsonFieldInit) :
		try :
			self._from = jsonFieldInit["_from"]
			self._to = jsonFieldInit["_to"]
		except KeyError :
			self._from, self._to = None, None
		Document.setPrivates(self, jsonFieldInit)

	def links(self, fromVertice, toVertice, **edgeArgs) :
		"an alias of save that works only for first saves. It will also trigger the saving of fromVertice and toVertice"
		if self.URL is not None :
			raise AttributeError("It appears that the edge has already been saved. You can now use save() and patch()")
		
		fromVertice.save()
		toVertice.save()

		self.save(fromVertice, toVertice, **edgeArgs)

	def save(self, fromVertice = None, toVertice = None, **edgeArgs) :
		"Works like Document's except that the irst time you save an Edge you must specify the 'from' and 'to' vertices. If you fear forgetting there's a links() function especially for first saves"
		if self.URL is None and (fromVertice is None or toVertice is None) :
			raise ValueError("The first time you save an Edge you must specify the 'from' and 'to' vertices")

		if fromVertice.__class__ is Document :
			fromId = fromVertice._id
		elif (type(fromVertice) is types.StringType) or (type(fromVertice) is types.UnicodeType) :
			fromId = fromVertice
		else :
			raise ValueError("fromVertice must be either a Document or a String")
		
		if toVertice.__class__ is Document :
			toId = toVertice._id
		elif (type(toVertice) is types.StringType) or (type(toVertice) is types.UnicodeType) :
			toId = toVertice
		else :
			raise ValueError("toVertice must be either a Document or a String")

		edgeArgs["from"] = fromId
		edgeArgs["to"] = toId
		
		self._from = fromId
		self._to = toId
		Document.save(self, **edgeArgs)

	def __str__(self) :
		return 'ArangoEdge: ' + str(self._store)

	def __repr__(self) :
		return 'ArangoEdge: ' + repr(self._store)