// Twenty-four columns rather than twelve, and rows half as tall, so a widget
// can be placed where it looks right rather than where the grid allows. Every
// number below is double what it was; the gutter is not, because it sits
// between widgets rather than between columns -- two of the new columns plus
// the gutter they no longer need between them come to exactly one of the old
// ones, so nothing changes size.
export default {
  columns: 24, // grid columns count
  rowHeight: 25, // grid row height (incl. bottom padding)
  margins: 15, // widget margins
  mobileBreakPoint: 800,
  // defaults for widgets
  defaultSizeX: 12,
  defaultSizeY: 6,
  minSizeX: 4,
  maxSizeX: 24,
  minSizeY: 4,
  maxSizeY: 2000,
};
