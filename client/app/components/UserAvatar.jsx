import React, { useState } from "react";
import PropTypes from "prop-types";
import cx from "classnames";

import { initials, tileColour } from "@/lib/initialsTile";

import "./UserAvatar.less";

/*
  A person's picture, or their initials.

  Every avatar in the product used to be a gravatar URL built from an MD5 of
  the email address. Three things wrong with that, in increasing order of
  importance:

  * It does not work offline. An air-gapped install drew a broken image in
    every list, beside every query, and logged a failed request for each.
  * It tells gravatar.com the MD5 of every email address in the organization,
    every time somebody opens a page, which is a disclosure nobody asked for
    from a tool whose selling point is that it runs on your own machines.
  * Almost nobody has a gravatar, so the usual result was the identicon --
    an abstract pattern that is no more recognisable than initials and costs
    a network round trip to fetch.

  So: initials, in a colour worked out from the name, drawn locally. A person
  who has set a picture still gets it; the disabled-account image still wins,
  because that one is saying something.
*/

export default function UserAvatar({ user, size, className }) {
  const [broken, setBroken] = useState(false);
  const label = (user && (user.name || user.email)) || "";
  const url = user && user.profile_image_url;

  if (url && !broken) {
    return (
      <img
        className={cx("user-avatar", className)}
        src={url}
        alt=""
        width={size}
        height={size}
        // A picture somebody set by URL can stop resolving -- the host goes
        // away, or the install loses the internet. The tile is a better
        // answer than a broken-image glyph.
        onError={() => setBroken(true)}
      />
    );
  }

  return (
    <span
      className={cx("user-avatar", "user-avatar-initials", className)}
      style={{
        backgroundColor: tileColour(label),
        width: size,
        height: size,
        fontSize: Math.max(7, Math.round(size * 0.42)),
      }}
      title={label}
      aria-hidden="true"
    >
      {initials(label)}
    </span>
  );
}

UserAvatar.propTypes = {
  user: PropTypes.shape({
    name: PropTypes.string,
    email: PropTypes.string,
    profile_image_url: PropTypes.string,
  }),
  size: PropTypes.number,
  className: PropTypes.string,
};

UserAvatar.defaultProps = {
  user: null,
  // What the lists use. The navbar and the preview card pass their own.
  size: 20,
  className: "",
};
