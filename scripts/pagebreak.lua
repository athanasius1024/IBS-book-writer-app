-- Pandoc Lua filter to convert page break divs to native page breaks
-- Handles <div style="page-break-after: always;"></div> and similar

function Div(el)
  -- Check if this is a page break div
  if el.attributes.style and 
     (string.find(el.attributes.style, "page%-break%-after") or 
      string.find(el.attributes.style, "page%-break%-before")) then
    -- Return a raw ODT page break
    return pandoc.RawBlock('opendocument', '<text:p text:style-name="Pagebreak"/>')
  end
  return el
end

-- Also handle raw HTML page breaks
function RawBlock(el)
  if el.format == 'html' and 
     (string.find(el.text, "page%-break%-after") or 
      string.find(el.text, "page%-break%-before")) then
    return pandoc.RawBlock('opendocument', '<text:p text:style-name="Pagebreak"/>')
  end
  return el
end
