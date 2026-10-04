import React from "react";
import PropTypes from "prop-types";
import classNames from "classnames";
import Link from "@/components/Link";
import TypeLogo from "@/components/TypeLogo";
import { IMG_ROOT } from "@/services/data-source";

// PreviewCard

export function PreviewCard({ image, imageUrl, roundedImage, title, body, children, className, ...props }) {
  return (
    <div {...props} className={className + " w-100 d-flex align-items-center"}>
      {image || (
        <img
          src={imageUrl}
          width="32"
          height="32"
          className={classNames({ "profile__image--settings": roundedImage }, "m-r-5")}
          alt="Logo/Avatar"
        />
      )}
      <div className="flex-fill">
        <div>{title}</div>
        {body && <div className="text-muted">{body}</div>}
      </div>
      {children}
    </div>
  );
}

PreviewCard.propTypes = {
  // Either a URL, which is drawn as a plain image, or an already-rendered one.
  image: PropTypes.node,
  imageUrl: PropTypes.string,
  title: PropTypes.node.isRequired,
  body: PropTypes.node,
  roundedImage: PropTypes.bool,
  className: PropTypes.string,
  children: PropTypes.node,
};

PreviewCard.defaultProps = {
  image: null,
  imageUrl: null,
  body: null,
  roundedImage: true,
  className: "",
  children: null,
};

// UserPreviewCard

export function UserPreviewCard({ user, withLink, children, ...props }) {
  const title = withLink ? <Link href={"users/" + user.id}>{user.name}</Link> : user.name;
  return (
    <PreviewCard {...props} imageUrl={user.profile_image_url} title={title} body={user.email}>
      {children}
    </PreviewCard>
  );
}

UserPreviewCard.propTypes = {
  user: PropTypes.shape({
    profile_image_url: PropTypes.string.isRequired,
    name: PropTypes.string.isRequired,
    email: PropTypes.string.isRequired,
  }).isRequired,
  withLink: PropTypes.bool,
  children: PropTypes.node,
};

UserPreviewCard.defaultProps = {
  withLink: false,
  children: null,
};

// DataSourcePreviewCard

export function DataSourcePreviewCard({ dataSource, withLink, children, ...props }) {
  const title = withLink ? <Link href={"data_sources/" + dataSource.id}>{dataSource.name}</Link> : dataSource.name;
  const image = (
    <TypeLogo
      src={`${IMG_ROOT}/${dataSource.type}.png`}
      label={dataSource.type}
      width={32}
      className="m-r-5"
      alt={dataSource.type}
    />
  );
  return (
    <PreviewCard {...props} image={image} title={title}>
      {children}
    </PreviewCard>
  );
}

DataSourcePreviewCard.propTypes = {
  dataSource: PropTypes.shape({
    name: PropTypes.string.isRequired,
    type: PropTypes.string.isRequired,
  }).isRequired,
  withLink: PropTypes.bool,
  children: PropTypes.node,
};

DataSourcePreviewCard.defaultProps = {
  withLink: false,
  children: null,
};
