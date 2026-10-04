import React from "react";
import { mount } from "enzyme";

import TypeLogo from "./TypeLogo";

/*
  A data source logo is a file named after the type. Add a type without adding the
  file and the ten places that draw one each rendered the browser's broken-image
  glyph -- silently, because a 404 on an <img> is reported to nobody.

  Kafka shipped that way once. Mimir and MariaDB would have.
*/

describe("TypeLogo", () => {
  it("draws the image when there is one", () => {
    const logo = mount(<TypeLogo src="/static/images/db-logos/mysql.png" label="mysql" width={20} />);

    expect(logo.find("img").prop("src")).toBe("/static/images/db-logos/mysql.png");
    expect(logo.find(".type-logo-fallback").exists()).toBe(false);
  });

  it("falls back to a tile when the file is missing", () => {
    const logo = mount(<TypeLogo src="/static/images/db-logos/mimir.png" label="mimir" width={20} />);
    logo.find("img").simulate("error");

    expect(logo.find("img").exists()).toBe(false);
    expect(logo.find(".type-logo-fallback").text()).toBe("MI");
  });

  it("falls back immediately when there is no source at all", () => {
    const logo = mount(<TypeLogo label="mariadb" width={32} />);

    expect(logo.find("img").exists()).toBe(false);
    expect(logo.find(".type-logo-fallback").text()).toBe("MA");
  });

  it("takes an initial from each word, so a type is not just its first letters", () => {
    expect(mount(<TypeLogo label="Grafana Mimir" />).text()).toBe("GM");
    expect(mount(<TypeLogo label="kafka_stream" />).text()).toBe("KS");
    expect(mount(<TypeLogo label="cloudwatch-insights" />).text()).toBe("CI");
  });

  it("gives a type the same colour every time", () => {
    const once = mount(<TypeLogo label="mimir" />)
      .find(".type-logo-fallback")
      .prop("style").backgroundColor;
    const again = mount(<TypeLogo label="mimir" />)
      .find(".type-logo-fallback")
      .prop("style").backgroundColor;

    expect(once).toBe(again);
    expect(once).toMatch(/^#[0-9a-f]{6}$/);
  });

  it("sizes itself inline only when asked to", () => {
    // CardsList sizes its logos from its own stylesheet, at three breakpoints. An
    // inline width would win against the narrow ones.
    const sized = mount(<TypeLogo label="mimir" width={64} />)
      .find(".type-logo-fallback")
      .prop("style");
    expect(sized.width).toBe(64);
    expect(sized.height).toBe(64);

    const unsized = mount(<TypeLogo label="mimir" />)
      .find(".type-logo-fallback")
      .prop("style");
    expect(unsized.width).toBeUndefined();
    expect(unsized.height).toBeUndefined();
  });

  it("says what it is to anyone who cannot see it", () => {
    const logo = mount(<TypeLogo label="mimir" alt="Grafana Mimir" />);
    const tile = logo.find(".type-logo-fallback");

    expect(tile.prop("role")).toBe("img");
    expect(tile.prop("aria-label")).toBe("Grafana Mimir");
  });

  it("stops being broken when the source changes to one that works", () => {
    const logo = mount(<TypeLogo src="/missing.png" label="mimir" width={20} />);
    logo.find("img").simulate("error");
    expect(logo.find("img").exists()).toBe(false);

    logo.setProps({ src: "/static/images/db-logos/mysql.png" });
    expect(logo.find("img").prop("src")).toBe("/static/images/db-logos/mysql.png");
  });
});
