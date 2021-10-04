import wx
import os
import sys
import time
from datetime import datetime, timedelta
import sqlite3
import CVUtil
from collections import namedtuple, defaultdict
from threading import RLock

from queue import Queue, Empty

import unicodedata
def removeDiacritic( s ):
	return unicodedata.normalize('NFKD', '{}'.format(s)).encode('ascii', 'ignore').decode()

now = datetime.now

def _createTable( c, table, fields ):
	def default_str( d ):
		return ' DEFAULT {}'.format(d) if d is not None else ''
	
	c.execute(
		'CREATE TABLE IF NOT EXISTS {} ({})'.format(table, ','.join('{} {}{}'.format(
				field, type, default_str(default)
			)
			for field, type, idx, default in fields ) )
	)
	for field, type, idx, default in fields:
		if idx:
			c.execute( 'CREATE INDEX IF NOT EXISTS {}_{}_idx on {} ({} ASC)'.format(table, field, table, field) )

class Database:

	UpdateSeconds = 10*60*60

	triggerFieldsAll = (
		'id','ts','s_before','s_after','ts_start','closest_frames','bib','first_name','last_name','team','wave','race_name',
		'note','kmh','frames',
		'finish_direction',
		'zoom_frame', 'zoom_x', 'zoom_y', 'zoom_width', 'zoom_height',
	)
	TriggerRecord = namedtuple( 'TriggerRecord', triggerFieldsAll )
	triggerFieldsInput = set(triggerFieldsAll) - {'id', 'note', 'kmh', 'frames', 'finish_direction', 'zoom_frame', 'zoom_x', 'zoom_y', 'zoom_width', 'zoom_height',}	# Fields to compare for equality of triggers.
	triggerFieldsUpdate = ('wave','race_name',)
	triggerEditFields = ('bib', 'first_name', 'last_name', 'team', 'wave', 'race_name', 'note',)
	
	def __init__( self, fname=None, initTables=True, fps=30 ):
		self.fname = (fname or os.path.join( os.path.expanduser("~"), 'CrossMgrVideo.sqlite3' ) )
		self.fps = fps
		
		'''
		try:
			print( 'database bytes: {}'.format( os.stat(self.fname).st_size ) )
		except Exception:
			pass
		'''
		
		# Use the RLock so that we serialize writes ourselves.  This allows use to share the same sqlite3 instance between threads.
		self.dbLock = RLock()
		self.conn = sqlite3.connect( self.fname, detect_types=sqlite3.PARSE_DECLTYPES, timeout=45.0, check_same_thread=False )
		
		if initTables:
			with self.dbLock, self.conn:
				# Add missing database fields.
				cur = self.conn.cursor()
				cur.execute( 'PRAGMA table_info(trigger)' )
				cols = cur.fetchall()
				if cols:
					col_names = {col[1] for col in cols}
					if 'note' not in col_names:
						self.conn.execute( 'ALTER TABLE trigger ADD COLUMN note TEXT DEFAULT ""' )
					if 'kmh' not in col_names:
						self.conn.execute( 'ALTER TABLE trigger ADD COLUMN kmh DOUBLE DEFAULT 0.0' )
					if 'ts_start' not in col_names:
						self.conn.execute( 'ALTER TABLE trigger ADD COLUMN ts_start timestamp DEFAULT 0' )
						self.conn.execute( 'UPDATE trigger SET ts_start=ts' )
					# Seconds before and after the ts time that frames were captured.
					if 's_before' not in col_names:
						self.conn.execute( 'ALTER TABLE trigger ADD COLUMN s_before DOUBLE DEFAULT 0.0' )
						self.conn.execute( 'ALTER TABLE trigger ADD COLUMN s_after DOUBLE DEFAULT 0.0' )
					# Cache of number of frames.
					if 'frames' not in col_names:
						self.conn.execute( 'ALTER TABLE trigger ADD COLUMN frames INTEGER DEFAULT 0' )
					# Closest frames queries.
					if 'closest_frames' not in col_names:
						self.conn.execute( 'ALTER TABLE trigger ADD COLUMN closest_frames INTEGER DEFAULT 0' )
					if 'finish_direction' not in col_names:
						self.conn.execute( 'ALTER TABLE trigger ADD COLUMN finish_direction INTEGER DEFAULT 0' )
					# Zoom window.
					if 'zoom_frame' not in col_names:
						self.conn.execute( 'ALTER TABLE trigger ADD COLUMN zoom_frame  INTEGER DEFAULT -1' )
						self.conn.execute( 'ALTER TABLE trigger ADD COLUMN zoom_x      INTEGER DEFAULT 0' )
						self.conn.execute( 'ALTER TABLE trigger ADD COLUMN zoom_y      INTEGER DEFAULT 0' )
						self.conn.execute( 'ALTER TABLE trigger ADD COLUMN zoom_width  INTEGER DEFAULT 0' )
						self.conn.execute( 'ALTER TABLE trigger ADD COLUMN zoom_height INTEGER DEFAULT 0' )
		
				_createTable( self.conn, 'photo', (
						('id', 'INTEGER PRIMARY KEY', False, None),
						('ts', 'timestamp', 'ASC', None),
						('jpg', 'BLOB', False, None),
					)
				)		
				_createTable( self.conn, 'trigger', (
						('id', 'INTEGER PRIMARY KEY', False, None),
						('ts', 'timestamp', 'ASC', None),			# Capture timestamp.
						('ts_start', 'timestamp', False, None),		# race timestamp.
						('s_before', 'DOUBLE', False, None),		# Seconds before ts of capture.
						('s_after', 'DOUBLE', False, None),			# Seconds after ts of capture.
						('closest_frames', 'INTEGER', False, 0),	# Number of frames if a closest Frames trigger.
						('bib', 'INTEGER', 'ASC', None),
						('first_name', 'TEXT', 'ASC', None),
						('last_name', 'TEXT', 'ASC', None),
						('team', 'TEXT', 'ASC', None),
						('wave', 'TEXT', 'ASC', None),
						('race_name', 'TEXT', 'ASC', None),
						('note', 'TEXT', False, None),
						('kmh', 'DOUBLE', False, 0.0),
						('frames', 'INTEGER', False, 0),			# Number of frames with this trigger.
						
						('finish_direction', 'INTEGER', False, 0),	# 0 == unspecified, 1 == left to right, 2 == right to left.
						
						('zoom_frame',	'INTEGER', False, -1),		# Frame of the best zoom image.  -1 means the Trigger frame.
						('zoom_x', 		'INTEGER', False, 0),		# Zoom x coord
						('zoom_y', 		'INTEGER', False, 0),		# Zoom y coord
						('zoom_width',	'INTEGER', False, 0),		# Zoom width
						('zoom_height', 'INTEGER', False, 0),		# Zoom height
					)
				)
				self.lastTsPhotos = set( row[0] for row in self.conn.execute(
						'SELECT ts FROM photo WHERE ts BETWEEN ? AND ?', (now() - timedelta(seconds=self.UpdateSeconds), now())
					)
				)
				
			self.deleteExistingTriggerDuplicates()
			self.deleteDuplicatePhotos()
		else:
			self.lastTsPhotos = set()
		
		self.lastUpdate = now() - timedelta(seconds=self.UpdateSeconds)
		
		self.tsJpgsKeyLast = None
		self.tsJpgsLast = None

	def clone( self ):
		return Database( self.fname, initTables=False, fps=self.fps )
		
	def getfname( self ):
		return self.fname
		
	def getsize( self ):
		with self.dbLock:
			try:
				return os.path.getsize( self.fname )
			except Exception:
				return None
	
	def _purgeTriggerWriteDuplicates( self, tsTriggers ):
		""" Remove all triggers that are already in the database. """
		return [trig for trig in tsTriggers
			if self.conn.execute(
						'SELECT id FROM trigger WHERE {}'.format(' AND '.join('{}=?'.format(f) for f in self.triggerFieldsInput)),
						[trig[f] for f in self.triggerFieldsInput]
					).fetchone() is None
		]
	
	def write( self, tsTriggers=None, tsJpgs=None ):
		with self.dbLock, self.conn:
			tsTriggers = self._purgeTriggerWriteDuplicates( tsTriggers )
			if not tsTriggers and not tsJpgs:
				return
		
			for trig in tsTriggers:
				self.conn.execute( 'INSERT INTO trigger ({}) VALUES ({})'.format(','.join(trig.keys()), ','.join('?'*len(trig))), list(trig.values()) )

			if tsJpgs:
				# Purge duplicate photos and photos with the same timestamp.
				jpgSeen = set()
				tsJpgsUnique = []
				for ts, jpg in tsJpgs:
					if ts and jpg and ts not in self.lastTsPhotos and jpg not in jpgSeen:
						self.lastTsPhotos.add( ts )
						jpgSeen.add( jpg )
						tsJpgsUnique.append( (ts, jpg) )
						
				tsJpgs = tsJpgsUnique
			
			if tsJpgs:
				self.conn.executemany( 'INSERT INTO photo (ts,jpg) VALUES (?,?)', tsJpgs )
		
		if (now() - self.lastUpdate).total_seconds() > self.UpdateSeconds:
			expired = now() - timedelta(seconds=self.UpdateSeconds)
			self.lastTsPhotos = set( ts for ts in self.lastTsPhotos if ts > expired )
			self.lastUpdate = now()
	
	def updateTriggerRecord( self, id, data ):
		if data:
			with self.dbLock, self.conn:
				self.conn.execute( 'UPDATE trigger SET {} WHERE id=?'.format(','.join('{}=?'.format(f) for f in data.keys())),
					list(data.values()) + [id]
				)
		return True
		
	def getTriggerFields( self, id, fieldNames=None ):
		if not fieldNames:
			fieldNames = self.triggerFieldsAll
		with self.dbLock, self.conn:
			row = self.conn.execute( 'SELECT {} FROM trigger WHERE id=?'.format(','.join(fieldNames)), (id,) ).fetchone()
		return { f:row[i] for i, f in enumerate(fieldNames) }
	
	def updateTriggerKMH( self, id, kmh ):
		self.updateTriggerRecord(id, {'kmh':kmh})
	
	def updateTriggerBeforeAfter( self, id, s_before, s_after ):
		self.updateTriggerRecord(id, {'s_before':s_before, 's_after':s_after})
	
	def initCaptureTriggerData( self, id ):
		''' Initialize some fields from the previous record. '''
		with self.dbLock, self.conn:
			rows = list( self.conn.execute( 'SELECT ts FROM trigger WHERE id=?', (id,) ) )
			if not rows:
				return
			ts = rows[0][0]
			tsLower, tsUpper = ts - timedelta(days=1), ts, 
			rows = list( self.conn.execute( 
				'SELECT {} FROM trigger WHERE ? < ts AND ts < ? ORDER BY ts DESC LIMIT 1'.format(','.join(self.triggerFieldsUpdate)),
					(tsLower, tsUpper)
				)
			)
			if rows:
				self.conn.execute(
					'UPDATE trigger SET {} WHERE id=?'.format(','.join('{}=?'.format(f) for f in self.triggerFieldsUpdate)),
						rows[0] + (id,)
				)
	
	def getTriggers( self, tsLower, tsUpper, bib=None ):
		with self.dbLock, self.conn:
			if not bib:
				triggers = self.conn.execute(
					'SELECT {} FROM trigger WHERE ts BETWEEN ? AND ? ORDER BY ts'.format(','.join(self.triggerFieldsAll)),
					(tsLower, tsUpper)
				)
			else:
				triggers = self.conn.execute(
					'SELECT {} FROM trigger WHERE bib=? AND ts BETWEEN ? AND ? ORDER BY ts'.format(','.join(self.triggerFieldsAll)),
					(bib, tsLower, tsUpper)
				)
				
			return [self.TriggerRecord(*trig) for trig in triggers]
	
	def _deleteIds( self, table, ids ):
		chunk_size = 500
		while ids:
			to_delete = ids[-chunk_size:]
			self.conn.execute( 'DELETE FROM {} WHERE id IN ({})'.format(table, ','.join('?'*len(to_delete))), to_delete )
			del ids[-chunk_size:]
	
	def _purgeDuplicateTS( self, tsJpgIdIter ):
		tsSeen = set()
		duplicateIds = []
		for ts, jpgId in tsJpgIdIter:
			if ts not in tsSeen:
				tsSeen.add( ts )
				yield ts, jpgId
			else:
				duplicateIds.append( jpgId )
		self._deleteIds( 'photo', duplicateIds )
		
	def _getPhotosPurgeDuplicateTS( self, tsLower, tsUpper ):
		tsJpgs = []
		tsSeen = set()
		duplicateIds = []
		for jpgId, ts, jpg in self.conn.execute( 'SELECT id,ts,jpg FROM photo WHERE ts BETWEEN ? AND ? ORDER BY ts', (tsLower, tsUpper) ):
			if ts and jpg and ts not in tsSeen:
				tsSeen.add( ts )
				tsJpgs.append( (ts, jpg) )
			else:
				duplicateIds.append( jpgId )
		self._deleteIds( 'photo', duplicateIds )
		return tsJpgs
		
	def _getPhotoCount( self, tsLower, tsUpper ):
		return sum( 1 for ts,jpgId in self._purgeDuplicateTS(self.conn.execute( 'SELECT ts,id FROM photo WHERE ts BETWEEN ? AND ?', (tsLower, tsUpper))) )
	
	def getPhotos( self, tsLower, tsUpper ):
		# Cache the results of the last query.
		key = (tsLower, tsUpper)
		if key == self.tsJpgsKeyLast:
			return self.tsJpgsLast
		
		with self.dbLock, self.conn:
			tsJpgs = self._getPhotosPurgeDuplicateTS( *key )
		
		self.tsJpgsKeyLast, self.tsJpgsLast = key, tsJpgs
		return tsJpgs
	
	def getPhotosClosest( self, ts, closestFrames ):
		# Cache the results of the last query.
		key = (ts, closestFrames)
		if key == self.tsJpgsKeyLast:
			return self.tsJpgsLast
			
		with self.dbLock, self.conn:
			for ts, jpg in self.conn.execute( 'SELECT ts,jpg FROM photo WHERE ts <= ? ORDER BY ts DESC', (ts,) ):
				tsEarlier, jpgEarlier = ts, jpg
				break
			else:
				tsEarlier, jpgEarlier = None, None
			
			for ts, jpg in self.conn.execute( 'SELECT ts,jpg FROM photo WHERE ts > ? ORDER BY ts ASC', (ts,) ):
				tsLater, jpgLater = ts, jpg
				break
			else:
				tsLater, jpgLater = None, None

		# Only works for closestFrames == 1 and closestFrames == 2
		if closestFrames == 1:
			tsJpgs = [(tsEarlier, jpgEarlier) if (tsLater is None or abs((tsEarlier - ts).total_seconds()) < abs((tsLater - ts).total_seconds())) else (tsLater, jpgLater)]
		else:
			tsJpgs = [p for p in [(tsEarlier,jpgEarlier), (tsLater,jpgLater)] if p[1]]
		
		self.tsJpgsKeyLast, self.tsJpgsLast = key, tsJpgs
		return tsJpgs
	
	def _getPhotosClosestIds( self, ts, closestFrames ):
		for ts, id in self.conn.execute( 'SELECT ts,id FROM photo WHERE ts <= ? ORDER BY ts DESC', (ts,) ):
			tsEarlier, idEarlier = ts, id
			break
		else:
			tsEarlier, idEarlier = None, None
		
		for ts, id in self.conn.execute( 'SELECT ts,id FROM photo WHERE ts > ? ORDER BY ts ASC', (ts,) ):
			tsLater, idLater = ts, id
			break
		else:
			tsLater, idLater = None, None

		# Only works for closestFrames == 1 and closestFrames == 2
		if closestFrames == 1:
			tsJpgIds = [(tsEarlier, idEarlier) if (tsLater is None or abs((tsEarlier - ts).total_seconds()) < abs((tsLater - ts).total_seconds())) else (tsLater, idLater)]
		else:
			tsJpgIds = [p for p in [(tsEarlier,idEarlier), (tsLater,idLater)] if p[1]]
		return tsJpgIds
	
	def getPhotoClosest( self, ts ):
		tsJpgs = self.getPhotosClosest( ts, 1 )
		return tsJpgs[0] if tsJpgs else (None, None)
	
	def getTriggerPhotoCount( self, id, s_before_default=0.5,  s_after_default=2.0 ):
		with self.dbLock, self.conn:
			trigger = list( self.conn.execute( 'SELECT ts,s_before,s_after FROM trigger WHERE id=?', (id,) ) )
			if not trigger:
				return 0
			ts, s_before, s_after = trigger[0]
			if s_before == 0.0 and s_after == 0.0:
				s_before, s_after = s_before_default, s_after_default
			tsLower, tsUpper = ts - timedelta(seconds=s_before), ts + timedelta(seconds=s_after)
			return self._getPhotoCount(tsLower, tsUpper)
		
	def updateTriggerPhotoCount( self, id, frames=None ):
		with self.dbLock, self.conn:
			frames = frames or self.getTriggerPhotoCount( id )
			self.conn.execute( 'UPDATE trigger SET frames=? WHERE id=? AND frames!=?', (frames, id, frames) )
			return frames
	
	def getPhotoById( self, id ):
		with self.dbLock, self.conn:
			row = self.conn.execute( 'SELECT jpg FROM photo WHERE id=?', (id,) ).fetchone()
		if row is None:
			raise ValueError( 'Nonexistent photo id={}'.format(id) )
		return row[0]		
	
	
	def queryTriggers( self, tsLower, tsUpper, bib=None ):
		triggers = self.getTriggers( tsLower, tsUpper, bib )
		trigs = []
		with self.dbLock, self.conn:
			for trig in triggers:
				trigCur = trig._asdict()
				if trig.closest_frames:
					trigCur['tsJpgIds'] = self._getPhotosClosestIds( trig.ts, trig.closest_frames )
				else:
					trigCur['tsJpgIds'] = list( self._purgeDuplicateTS(
						self.conn.execute( 'SELECT ts,id FROM photo WHERE ts BETWEEN ? and ?',
							(trig.ts - timedelta(seconds=trig.s_before), trig.ts + timedelta(seconds=trig.s_after)) ) 
						)
					)
				trigs.append( trigCur )
		return trigs
	
	def getTriggerPhotoCounts( self, tsLower, tsUpper ):
		counts = defaultdict( int )
		with self.dbLock, self.conn:
			triggers = { r[0]:(r[1]-timedelta(seconds=r[2]), r[1]+timedelta(seconds=r[3])) for r in self.conn.execute(
				'SELECT id,ts,s_before,s_after FROM trigger WHERE ts BETWEEN ? AND ?', (tsLower, tsUpper)
			) }
			if not triggers:
				return counts
			tsLowerPhoto = min( tsBefore for tsBefore,tsAfter in triggers.values() )
			tsUpperPhoto = max( tsAfter  for tsBefore,tsAfter in triggers.values() )
			rangeSecs = (tsUpperPhoto - tsLowerPhoto).total_seconds()
			if rangeSecs == 0.0:
				return counts
			
			# Create a bucket list containing every intersecting trigger interval.
			bucketMax = min( len(triggers)*2+10, 256 )
			bucketSecs = (rangeSecs + 0.001) / bucketMax	# Ensure the timestamps equal to tsUpperPhoto go into the last bucket.
			def tsToB( ts ):
				return int((ts - tsLowerPhoto).total_seconds() / bucketSecs)
			buckets = [[] for b in range(bucketMax)]
			for id, (tsBefore,tsAfter) in triggers.items():
				for b in range(tsToB(tsBefore), tsToB(tsAfter)+1):
					buckets[b].append(id)
					
			# Increment the count for every trigger intersecting this photo in the bucket.
			for r in self.conn.execute( 'SELECT ts FROM photo WHERE ts BETWEEN ? AND ?', (tsLowerPhoto, tsUpperPhoto) ):
				tsPhoto = r[0]
				for id in buckets[tsToB(tsPhoto)]:
					tsBefore,tsAfter = triggers[id]
					if tsBefore <= tsPhoto <= tsAfter:
						counts[id] += 1
		return counts
	
	def updateTriggerPhotoCounts( self, counts ):
		with self.dbLock, self.conn:
			self.conn.executemany( 'UPDATE trigger SET frames=? WHERE id=? AND frames!=?',
				[(count, id, count) for id, count in counts.items()]
			)
	
	def getLastPhotos( self, count ):
		with self.dbLock, self.conn:
			tsJpgs = list( self.conn.execute( 'SELECT ts,jpg FROM photo ORDER BY ts DESC LIMIT ?', (count,)) )
		tsJpgs.reverse()
		return tsJpgs
	
	def getLastTimestamp( self, tsLower, tsUpper ):
		with self.dbLock, self.conn:
			c = self.conn.cursor()
			c.execute( 'SELECT ts FROM trigger WHERE ts BETWEEN ? AND ? ORDER BY ts', (tsLower, tsUpper) )
			return c.fetchone()[0]
		
	def getTimestampRange( self ):
		with self.dbLock, self.conn:
			c = self.conn.cursor()
			c.execute( 'SELECT ts FROM trigger ORDER BY ts ASC' )
			row = c.fetchone()
			if not row:
				return None, None
			trigFirst = row[0]
			c.execute( 'SELECT ts FROM trigger ORDER BY ts DESC' )
			trigLast = c.fetchone()[0]
			return trigFirst, trigLast
	
	def getTriggerDates( self ):
		dates = defaultdict( int )
		with self.dbLock, self.conn:
			for row in self.conn.execute( 'SELECT ts FROM trigger' ):
				if row[0]:
					dates[row[0].date()] += 1
		return sorted( dates.items() )
	
	def getTriggerEditFields( self, id ):
		with self.dbLock, self.conn:
			rows = list( self.conn.execute('SELECT {} FROM trigger WHERE id=?'.format(','.join(self.triggerEditFields)), (id,) ) )
		return {k:v for k, v in zip(self.triggerEditFields, rows[0])} if rows else {}
		
	def setTriggerEditFields( self, id, **kwargs ):
		with self.dbLock, self.conn:
			self.conn.execute(
				'UPDATE trigger SET {} WHERE id=?'.format(','.join('{}=?'.format(f) for f in kwargs.keys())),
				list(kwargs.values()) + [id]
			)
	
	def isDup( self, ts ):
		return ts in self.lastTsPhotos
		
	def deleteExistingTriggerDuplicates( self ):
		with self.dbLock, self.conn:
			rowPrev = None
			duplicateIds = []
			for row in self.conn.execute( 'SELECT id,{} from trigger ORDER BY ts ASC,kmh DESC'.format(','.join(self.triggerFieldsInput)) ):
				if rowPrev is not None and row[1:] == rowPrev[1:]:
					duplicateIds.append( rowPrev[0] )
				else:
					rowPrev = row
		
			self._deleteIds( 'trigger', duplicateIds )
		
	def deleteDuplicatePhotos( self ):
		tsSeen = set()
		duplicateIds = []
		with self.dbLock, self.conn:
			for jpgId, ts in self.conn.execute( 'SELECT id,ts FROM photo ORDER BY ts DESC' ):
				if ts and ts not in tsSeen:
					tsSeen.add( ts )
				else:
					duplicateIds.append( jpgId )
			self._deleteIds( 'photo', duplicateIds )
	
	def cleanBetween( self, tsLower, tsUpper ):
		if not tsLower and not tsUpper:
			return
			
		tsLower = tsLower or datetime.datetime(1900,1,1,0,0,0)
		tsUpper = tsUpper or datetime.datetime(datetime.datetime.now().year+1000,1,1,0,0,0)
	
		with self.dbLock, self.conn:
			self.conn.execute( 'DELETE from photo WHERE ts BETWEEN ? AND ?', (tsLower,tsUpper) )
			self.conn.execute( 'DELETE from trigger WHERE ts BETWEEN ? AND ?', (tsLower,tsUpper) )
	
	def deleteTrigger( self, id, s_before_default=0.5,  s_after_default=2.0 ):
		def getClosestBeforeAfter( ts, closest_frames ):
			tsJpgs = self.getPhotosClosest( ts, closest_frames )
			if not tsJpgs:
				return 0.0, 0.0
			s_before = (ts - tsJpgs[0][0]).total_seconds()
			s_after = (tsJpgs[-1][0] - ts).total_seconds()
			return s_before, s_after
		
		with self.dbLock, self.conn:
			rows = list( self.conn.execute( 'SELECT ts,s_before,s_after,closest_frames FROM trigger WHERE id=?', (id,) ) )
			if not rows:
				return
			
			ts, s_before, s_after, closest_frames = rows[0]
			self.conn.execute( 'DELETE FROM trigger WHERE id=?', (id,) )
			
		if closest_frames:
			s_before, s_after = getClosestBeforeAfter( ts, closest_frames )
		
		tsLower, tsUpper = ts - timedelta(seconds=s_before), ts + timedelta(seconds=s_after)
				
		with self.dbLock, self.conn:
			# Get all other intervals that intersect this one.
			triggers = list( self.conn.execute( 'SELECT ts,s_before,s_after,closest_frames FROM trigger WHERE ts BETWEEN ? AND ?',
					(tsLower - timedelta(minutes=15),tsUpper + timedelta(minutes=15)) )
			)
			
		intervals = []
		for ts,s_before,s_after,closest_frames in triggers:
			if closest_frames:
				s_before, s_after = getClosestBeforeAfter( ts, closest_frames )
			elif s_before == 0.0 and s_after == 0.0:
				s_before, s_after = s_before_default, s_after_default
			
			tsStart, tsEnd = ts - timedelta(seconds=s_before), ts + timedelta(seconds=s_after)
			if tsEnd <= tsLower or tsUpper <= tsStart:
				continue
			intervals.append( (max(tsLower,tsStart), min(tsUpper,tsEnd)) )
		
		# Merge overlapping and adjacent intervals together.
		if intervals:
			intervals.sort()
			intervalsNormal = [intervals[0]]
			for a, b in intervals[1:]:
				if a <= intervalsNormal[-1][1]:
					if b > intervalsNormal[-1][1]:
						intervalsNormal[-1] = (intervalsNormal[-1][0], b)
				elif a != b:
					intervalsNormal.append( (a, b) )
			intervals = intervalsNormal

		toRemove = [(tsLower, tsUpper)]
		for a, b in intervals:
			# Split the last interval to accommodate the interval.
			u, v = toRemove.pop()
			if u != a:
				toRemove.append( (u, a) )
			if b != v:
				toRemove.append( (b, v) )

		if toRemove:
			with self.dbLock, self.conn:
				for a, b in toRemove:
					self.conn.execute( 'DELETE from photo WHERE ts BETWEEN ? AND ?', (a,b) )
			
	def vacuum( self ):
		with self.dbLock, self.conn:
			self.conn.execute( 'VACUUM' )

dbGlobal = None
def GlobalDatabase( fname=None ):
	global dbGlobal
	if dbGlobal is None:
		dbGlobal = Database( fname=fname )
	return dbGlobal

tsJpgs = []
tsTriggers = []
def flush( db, triggerWriteCB = None ):
	if db:
		db.write( tsTriggers, tsJpgs )
		if tsTriggers and triggerWriteCB:
			triggerWriteCB()
	del tsTriggers[:]
	del tsJpgs[:]
		
def DBWriter( q, triggerWriteCB=None, fname=None ):
	db = GlobalDatabase( fname=fname )
	
	keepGoing = True
	while keepGoing:
		try:
			v = q.get( timeout=2 )
		except Empty:
			if tsTriggers or tsJpgs:
				flush( db, triggerWriteCB )
			continue
		
		doFlush = True
		if v[0] == 'photo':
			doFlush = False
			if not db.isDup( v[1] ):
				tsJpgs.append( (v[1], sqlite3.Binary(CVUtil.frameToJPeg(v[2]))) )
		elif v[0] == 'trigger':
			tsTriggers.append( v[1] )
		elif v[0] == 'kmh':
			db.updateTriggerKMH( v[1], v[2] )	# id, kmh
		elif v[0] == 'flush':
			pass
		elif v[0] == 'terminate':
			keepGoing = False
		
		if doFlush or len(tsJpgs) >= 30*3:
			flush( db, triggerWriteCB )
		q.task_done()
		
	flush( db )
	
if __name__ == '__main__':
	if False:
		try:
			os.remove( os.path.join( os.path.expanduser("~"), 'CrossMgrVideo.sqlite3' ) )
		except Exception:
			pass

	d = GlobalDatabase()
	
	ts = d.getLastTimestamp(datetime(2000,1,1), datetime(2200,1,1))
	print( ts )
	
	def printTriggers():
		qTriggers = 'SELECT {} FROM trigger ORDER BY ts LIMIT 8'.format(','.join(d.triggerFieldsInput))
		print( '*******************' )
		for row in d.conn.execute(qTriggers):
			print( removeDiacritic(','.join( '{}'.format(v) for v in row )) )
	
	# Create existing duplicateIds all the triggers.
	tsTriggers = d.conn.execute('SELECT {} FROM trigger'.format(','.join(d.triggerFieldsInput))).fetchall()
	d.conn.executemany(
		'INSERT INTO trigger ({}) VALUES ({})'.format(','.join(d.triggerFieldsInput), ','.join('?'*len(d.triggerFieldsInput))),
		tsTriggers
	)	
	printTriggers()
	
	# Delete the existing duplicates.
	d.deleteExistingTriggerDuplicates()
	printTriggers()
	
	# Now, test for checking duplicate triggers on add.
	d.write( tsTriggers, None )
	printTriggers()
	
	print( d.getTriggerDates() )
	
		
	'''
	tsTriggers = [((time.sleep(0.1) and False) or now(), 100+i, '', '', '', '', '') for i in range(100)]
	
	tsJpgs = [((time.sleep(0.01) and False) or now(), b'asdfasdfasdfasdfasdf') for i in range(100)]
	d.write( tsTriggers, tsJpgs )
	d.write( [], tsJpgs )
		
	print( len(d.getTriggers( now() - timedelta(seconds=5), now() )) )
	print( len(d.getPhotos( now() - timedelta(seconds=5), now() )) )
	'''
