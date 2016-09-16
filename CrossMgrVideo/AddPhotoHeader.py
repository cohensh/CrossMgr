import wx
from wx.lib.agw.aui import LightColour
import os
import math
import Utils

class dotdict( object ):
	pass

def formatTime( secs ):
	f, ss = math.modf( secs or 0.0 )
	
	secs = int(ss)
	hours = secs // (60*60)
	minutes = (secs // 60) % 60
	secs = secs % 60 + f
	return '{:02d}:{:02d}:{:06.3f}'.format( hours, minutes, secs )
	
def PilImageToWxImage( pil ):
	image = wx.EmptyImage( *pil.size )
	image.SetData( pil.convert('RGB').tobytes() )
	return image

drawResources = None		# Cached resource for drawing the photo header.
def setDrawResources( dc, w, h ):
	global drawResources
	drawResources = dotdict()
	
	drawResources.w = w
	drawResources.h = h
	
	fontHeight = int(h/36.0)
	fontFace = Utils.FontFace
	
	drawResources.bibFontSize = fontHeight * 1.5
	drawResources.bibFont = wx.FontFromPixelSize(
		wx.Size(0, drawResources.bibFontSize),
		wx.FONTFAMILY_SWISS, wx.NORMAL, wx.FONTWEIGHT_BOLD,
		face=fontFace,
	)
	
	dc.SetFont( drawResources.bibFont )
	drawResources.bibWidth, drawResources.bibHeight = dc.GetTextExtent( u' 9999' )
	drawResources.bibTextColour = wx.Colour(0,0,200)
	drawResources.bibSpaceWidth = dc.GetTextExtent( u'9999' )[0] / 4
	
	drawResources.nameFontSize = drawResources.bibFontSize
	drawResources.nameFont = wx.FontFromPixelSize(
		wx.Size(0, drawResources.nameFontSize),
		wx.FONTFAMILY_SWISS, wx.NORMAL, wx.FONTWEIGHT_NORMAL,
		face=fontFace,
	)
	drawResources.nameTextColour = drawResources.bibTextColour
	
	drawResources.fontSize = fontHeight * 1.0
	drawResources.font = wx.FontFromPixelSize(
		wx.Size(0, drawResources.fontSize),
		wx.FONTFAMILY_SWISS, wx.NORMAL, wx.FONTWEIGHT_NORMAL,
		face=fontFace,
	)
	dc.SetFont( drawResources.font )
	drawResources.spaceWidth = dc.GetTextExtent( u'9999' )[0] / 4
	
	drawResources.smallFontSize = drawResources.fontSize * 0.9
	drawResources.smallFont = wx.FontFromPixelSize(
		wx.Size(0, drawResources.smallFontSize),
		wx.FONTFAMILY_SWISS, wx.NORMAL, wx.FONTWEIGHT_NORMAL,
		face=fontFace,
	)
	drawResources.fontColour = wx.BLACK
	dc.SetFont( drawResources.font )
	drawResources.fontHeight = dc.GetTextExtent( u'ATWgjjy' )[1]
	
	bitmapHeight = drawResources.bibHeight * 2.8
	
	bitmap = wx.Bitmap( os.path.join(Utils.getImageFolder(), 'CrossMgrHeader.png'), wx.BITMAP_TYPE_PNG )
	scaleMult = float(bitmapHeight) / float(bitmap.GetHeight())
	
	image = bitmap.ConvertToImage()
	drawResources.bitmapWidth, drawResources.bitmapHeight = int(image.GetWidth() * scaleMult), int(image.GetHeight() * scaleMult)
	image.Rescale( drawResources.bitmapWidth, drawResources.bitmapHeight, wx.IMAGE_QUALITY_HIGH )
	
	drawResources.bitmap = image.ConvertToBitmap()
	
	drawResources.fadeDark = wx.Colour(114+80,119+80,168+80)
	drawResources.fadeLight = LightColour( drawResources.fadeDark, 50 )
	drawResources.borderColour = wx.Colour( 71+50, 75+50, 122+50 )

def AddPhotoHeader( bitmap, bib=None, ts=None, raceSeconds=None, firstName=u'', lastName=u'', team=u'', raceName=u'' ):
	global drawResources
	
	w, h = bitmap.GetSize()
	dcMemory = wx.MemoryDC( bitmap )
	dc = wx.GCDC( dcMemory )
	
	if drawResources is None or drawResources.w != w or drawResources.h != h:
		setDrawResources( dc, w, h )
	
	bibTxt = u'{}'.format(bib) if bib else u''
	if ts and raceSeconds:
		tsTxt = u'{}  {}'.format( formatTime(raceSeconds), ts.strftime('%Y-%m-%d %H:%M:%S') )
	elif ts:
		tsTxt = u'{}'.format( ts.strftime('%Y-%m-%d %H:%M:%S') )
	elif raceSeconds:
		tsTxt = u'{}'.format( formatTime(raceSeconds) )
	else:
		tsTxt = u''
	if tsTxt.startswith('0'):
		tsTxt = tsTxt[1:]
	nameTxt = u' '.join( n for n in [firstName, lastName] if n )
	
	frameWidth = 4
	borderWidth = 1
	
	bitmapWidth = drawResources.bitmapWidth
	bitmapHeight = drawResources.bitmapHeight
	bibSpaceWidth = drawResources.bibSpaceWidth
	spaceWidth = drawResources.spaceWidth
	xText, yText = bitmapWidth, 0
	
	x = borderWidth
	y = borderWidth
	
	def shadedRect( x, y, w, h ):
		highlightTop = int(h/4.0)
		dc.GradientFillLinear( wx.Rect(0, y, w, highlightTop),
			drawResources.fadeDark, drawResources.fadeLight, wx.SOUTH )
		dc.GradientFillLinear( wx.Rect(0, y+highlightTop, w, h-highlightTop),
			drawResources.fadeDark, drawResources.fadeLight, wx.NORTH )
	
	def textInRect( txt, x, y, width, height, font=None, colour=None, alignment=wx.ALIGN_CENTER|wx.ALIGN_CENTRE_VERTICAL ):
		if font:
			dc.SetFont( font )
		if colour:
			dc.SetTextForeground( colour )
		dc.DrawLabel( txt, wx.Rect(x, y, width, height), alignment )
	
	lineHeight = int(drawResources.bibHeight * 1.25 + 0.5)
	x += xText + frameWidth + bibSpaceWidth
	
	dc.SetPen( wx.Pen(drawResources.borderColour, borderWidth) )
	
	shadedRect( x, 0, w, lineHeight + borderWidth )

	dc.DrawLine( 0, 0, w, 0 )
	dc.DrawLine( xText, lineHeight, w, lineHeight )
	
	# Draw the bib.
	dc.SetFont( drawResources.bibFont )
	tWidth = dc.GetTextExtent( bibTxt )[0]
	textInRect( bibTxt, x, y, tWidth, lineHeight, drawResources.bibFont, drawResources.bibTextColour )

	# Draw the name and team.
	x += tWidth + spaceWidth
	textInRect( nameTxt, x, y, dc.GetTextExtent(nameTxt)[0], lineHeight, drawResources.nameFont, drawResources.bibTextColour )
	x += dc.GetTextExtent(nameTxt)[0] + spaceWidth
	remainingWidth = w - x - spaceWidth - borderWidth
	dc.SetFont( drawResources.font )
	teamWidth = dc.GetTextExtent(team)[0]
	if teamWidth < remainingWidth:
		textInRect( team, x, y, remainingWidth, lineHeight, drawResources.font, wx.BLACK, alignment=wx.ALIGN_RIGHT|wx.ALIGN_CENTRE_VERTICAL )
	
	y += lineHeight
	
	lineHeight = int( drawResources.fontHeight * 1.25 + 0.5 )
	shadedRect( 0, y, w, lineHeight )
	dc.DrawLine( 0, y+lineHeight, w, y+lineHeight )
	
	# Draw the ts, race ts and raceName.
	dc.SetFont( drawResources.font )
	x = borderWidth
	x += xText + frameWidth + bibSpaceWidth
	textInRect( tsTxt, x, y, w-x, lineHeight, drawResources.font, wx.BLACK, alignment=wx.ALIGN_LEFT|wx.ALIGN_CENTRE_VERTICAL )
	x += dc.GetTextExtent(tsTxt)[0] + spaceWidth
	remainingWidth = w - x - spaceWidth - borderWidth
	raceNameWidth = dc.GetTextExtent(raceName)[0]
	if raceNameWidth < remainingWidth:
		textInRect( raceName, x, y, remainingWidth, lineHeight, drawResources.font, wx.BLACK, alignment=wx.ALIGN_RIGHT|wx.ALIGN_CENTRE_VERTICAL )
	
	# Draw the bitmap.
	dc.DrawBitmap( drawResources.bitmap, frameWidth, frameWidth )
	
	# Draw a frame around the bitmap.
	dc.SetBrush( wx.TRANSPARENT_BRUSH )
	
	frameHalf = frameWidth / 2
	dc.SetPen( wx.Pen(drawResources.borderColour, frameWidth) )
	dc.DrawRectangle( frameHalf, frameHalf, bitmapWidth+frameHalf, bitmapHeight+frameHalf )
	dc.SetPen( wx.Pen(wx.WHITE, frameHalf) )
	dc.DrawRectangle( frameHalf, frameHalf, bitmapWidth+frameHalf, bitmapHeight+frameHalf )
	
	# Draw a border on the right side.
	dc.SetPen( wx.Pen(drawResources.borderColour, 1) )
	dc.DrawLine( w-1, 0, w-1, y+lineHeight )
	
	return wx.ImageFromBitmap( bitmap )
