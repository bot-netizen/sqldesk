import React from "react";
import { mount } from "enzyme";

import UserAvatar from "./UserAvatar";

/*
  Every avatar used to be a gravatar URL built from an MD5 of the email.
  Offline that drew a broken image beside every query, and online it told
  gravatar.com the MD5 of every address here on every page load.
*/

describe("UserAvatar", () => {
  it("draws the picture somebody set", () => {
    const wrapper = mount(<UserAvatar user={{ name: "Ana Flores", profile_image_url: "https://example.com/a.png" }} />);

    expect(wrapper.find("img").prop("src")).toBe("https://example.com/a.png");
    expect(wrapper.find(".user-avatar-initials").exists()).toBe(false);
  });

  it("draws initials when there is none", () => {
    const wrapper = mount(<UserAvatar user={{ name: "Ana Flores", profile_image_url: null }} />);

    expect(wrapper.find("img").exists()).toBe(false);
    expect(wrapper.find(".user-avatar-initials").text()).toBe("AF");
  });

  it("takes one letter from each of two names", () => {
    expect(mount(<UserAvatar user={{ name: "Ana Flores" }} />).text()).toBe("AF");
  });

  it("takes two letters from a single name, because one is not enough to tell rows apart", () => {
    expect(mount(<UserAvatar user={{ name: "Iqbal" }} />).text()).toBe("IQ");
  });

  it("falls back to the email when there is no name", () => {
    expect(mount(<UserAvatar user={{ email: "ana@example.com" }} />).text()).toBe("AN");
  });

  it("gives the same person the same colour every time", () => {
    // A colour that changes between renders is worse than no colour: the
    // point is finding a face in a list by its colour before reading it.
    const once = mount(<UserAvatar user={{ name: "Ana Flores" }} />)
      .find(".user-avatar-initials")
      .prop("style").backgroundColor;
    const again = mount(<UserAvatar user={{ name: "Ana Flores" }} />)
      .find(".user-avatar-initials")
      .prop("style").backgroundColor;

    expect(once).toBe(again);
    expect(once).toMatch(/^#[0-9a-f]{6}$/);
  });

  it("gives different people different colours", () => {
    const a = mount(<UserAvatar user={{ name: "Ana Flores" }} />)
      .find(".user-avatar-initials")
      .prop("style").backgroundColor;
    const b = mount(<UserAvatar user={{ name: "Bruno Tan" }} />)
      .find(".user-avatar-initials")
      .prop("style").backgroundColor;

    expect(a).not.toBe(b);
  });

  it("falls back to the tile when a picture stops resolving", () => {
    // A URL somebody set can die: the host goes away, or the install loses
    // the internet. A tile beats the browser's broken-image glyph.
    const wrapper = mount(<UserAvatar user={{ name: "Ana Flores", profile_image_url: "https://gone/a.png" }} />);
    wrapper.find("img").simulate("error");

    expect(wrapper.find("img").exists()).toBe(false);
    expect(wrapper.find(".user-avatar-initials").text()).toBe("AF");
  });

  it("draws something rather than nothing for a user it knows nothing about", () => {
    expect(mount(<UserAvatar user={{}} />).text()).toBe("?");
    expect(mount(<UserAvatar />).text()).toBe("?");
  });

  it("sizes itself, so a sidebar's 13px and a navbar's 24px are both legible", () => {
    const small = mount(<UserAvatar user={{ name: "Ana Flores" }} size={13} />)
      .find(".user-avatar-initials")
      .prop("style");
    const large = mount(<UserAvatar user={{ name: "Ana Flores" }} size={32} />)
      .find(".user-avatar-initials")
      .prop("style");

    expect(small.width).toBe(13);
    expect(large.width).toBe(32);
    expect(large.fontSize).toBeGreaterThan(small.fontSize);
  });
});
